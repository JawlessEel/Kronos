"""
Out-of-Sample Benchmark for Dual-Model SPY (23-Yr) + VIX Companion Confluence Predictor
and Full Suite Scoreboard across all 7 Multi-Timeframe Foundation Models.
"""
import json
import math
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import torch

ROOT = Path("/Volumes/MacMoneyMakerSSD/Ai_apps/kronos")
sys.path.insert(0, str(ROOT))
from model import Kronos, KronosTokenizer
from model.enhanced_predictor import EnhancedKronosPredictor
from model.confluence_predictor import SPYVIXConfluencePredictor

OUTPUT_DIR = ROOT / "outputs" / "spy_vix_confluence_benchmark"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LOOKBACK = 256
HORIZON = 24
NUM_WINDOWS = 30


def calc_binomial_pval(k, n, p=0.5):
    if n == 0:
        return 1.0
    return sum(math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) for i in range(k, n + 1))


def evaluate_confluence_pair(confluence, spy_csv, vix_csv, label):
    spy_df = pd.read_csv(spy_csv, parse_dates=["timestamps"]).tail(4000)
    vix_df = pd.read_csv(vix_csv, parse_dates=["timestamps"]).tail(4000)

    merged = pd.merge(
        spy_df, vix_df, on="timestamps", suffixes=("_spy", "_vix"), how="inner"
    ).sort_values("timestamps").reset_index(drop=True)

    spy_aligned = pd.DataFrame({
        "timestamps": merged["timestamps"],
        "open": merged["open_spy"],
        "high": merged["high_spy"],
        "low": merged["low_spy"],
        "close": merged["close_spy"],
        "volume": merged["volume_spy"],
        "amount": merged["amount_spy"],
    })
    vix_aligned = pd.DataFrame({
        "timestamps": merged["timestamps"],
        "open": merged["open_vix"],
        "high": merged["high_vix"],
        "low": merged["low_vix"],
        "close": merged["close_vix"],
        "volume": merged["volume_vix"],
        "amount": merged["amount_vix"],
    })

    print(f"\n--- {label}: Aligned {len(merged):,} held-out 1-hour bars ending {merged['timestamps'].iloc[-1]} ---")

    all_hits = 0
    total_valid = 0
    confirmed_hits = 0
    confirmed_total = 0
    spy_maes = []
    confirmed_maes = []
    records = []

    for w in range(NUM_WINDOWS, 0, -1):
        end_idx = len(merged) - (w * HORIZON)
        spy_hist = spy_aligned.iloc[end_idx - LOOKBACK : end_idx]
        vix_hist = vix_aligned.iloc[end_idx - LOOKBACK : end_idx]
        spy_actual = spy_aligned.iloc[end_idx : end_idx + HORIZON]
        vix_actual = vix_aligned.iloc[end_idx : end_idx + HORIZON]

        actual_spy_ret = (float(spy_actual["close"].iloc[-1]) / float(spy_hist["close"].iloc[-1]) - 1.0) * 100.0
        if abs(actual_spy_ret) < 0.05:
            continue

        res = confluence.predict(
            spy_df=spy_hist.reset_index(drop=True),
            vix_df=vix_hist.reset_index(drop=True),
            x_timestamp=spy_hist["timestamps"].reset_index(drop=True),
            y_timestamp=spy_actual["timestamps"].reset_index(drop=True),
            pred_len=HORIZON,
            T=0.2,
            top_p=0.9,
            sample_count=5,
        )

        actual_vix_ret = (float(vix_actual["close"].iloc[-1]) / res.vix_last_close - 1.0) * 100.0
        mae = float(np.mean(np.abs(res.spy_pred_df["close"].values - spy_actual["close"].values)))
        spy_maes.append(mae)

        spy_hit = bool(np.sign(res.spy_return_pct) == np.sign(actual_spy_ret))
        total_valid += 1
        if spy_hit:
            all_hits += 1

        if res.is_confirmed:
            confirmed_total += 1
            confirmed_maes.append(mae)
            if spy_hit:
                confirmed_hits += 1

        mark = "✓" if spy_hit else "✗"
        conf_tag = f"[{res.signal}]" if res.is_confirmed else "[FILTERED_CHOP]"
        print(
            f"  Win {w:02d} ({spy_actual['timestamps'].iloc[0]}) | SPY Actual: {actual_spy_ret:+.2f}% | "
            f"Pred SPY: {res.spy_return_pct:+.2f}% | Pred VIX: {res.vix_return_pct:+.2f}% | MAE: ${mae:.2f} | {mark} {conf_tag}"
        )

        records.append({
            "window": w,
            "timestamp": str(spy_actual["timestamps"].iloc[0]),
            "actual_spy_ret": actual_spy_ret,
            "actual_vix_ret": actual_vix_ret,
            "pred_spy_ret": res.spy_return_pct,
            "pred_vix_ret": res.vix_return_pct,
            "mae": mae,
            "signal": res.signal,
            "is_confirmed": res.is_confirmed,
            "conviction_score": res.conviction_score,
            "spy_hit": spy_hit,
        })

    unfiltered_acc = (all_hits / max(1, total_valid)) * 100.0
    confirmed_acc = (confirmed_hits / max(1, confirmed_total)) * 100.0
    avg_mae = float(np.mean(spy_maes))
    avg_conf_mae = float(np.mean(confirmed_maes)) if confirmed_maes else avg_mae
    pval_conf = calc_binomial_pval(confirmed_hits, confirmed_total)

    print(f"\n[{label} Summary]")
    print(f"  Unfiltered SPY Accuracy : {all_hits}/{total_valid} ({unfiltered_acc:.1f}%) | Avg MAE: ${avg_mae:.2f}")
    print(f"  VIX-Confirmed Only      : {confirmed_hits}/{confirmed_total} ({confirmed_acc:.1f}%) | Avg MAE: ${avg_conf_mae:.2f} | p-val: {pval_conf:.4f}")

    return {
        "label": label,
        "total_windows": total_valid,
        "unfiltered_hits": all_hits,
        "unfiltered_accuracy": unfiltered_acc,
        "unfiltered_avg_mae": avg_mae,
        "confirmed_trades": confirmed_total,
        "confirmed_hits": confirmed_hits,
        "confirmed_accuracy": confirmed_acc,
        "confirmed_avg_mae": avg_conf_mae,
        "confirmed_p_value": pval_conf,
        "records": records,
    }


def evaluate_single_model(model_name, csv_path, norm_mode="detrend", num_win=25):
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    m_dir = ROOT / "finetune_csv" / "finetuned" / model_name
    pred = EnhancedKronosPredictor(
        Kronos.from_pretrained(str(m_dir / "basemodel" / "best_model")),
        KronosTokenizer.from_pretrained(str(m_dir / "tokenizer" / "best_model")),
        device=device,
        max_context=512,
    )
    df = pd.read_csv(csv_path, parse_dates=["timestamps"]).tail(4000).reset_index(drop=True)
    hits, tot = 0, 0
    maes, mapes = [], []
    for w in range(num_win, 0, -1):
        end = len(df) - w * HORIZON
        hist = df.iloc[end - LOOKBACK : end].reset_index(drop=True)
        act = df.iloc[end : end + HORIZON].reset_index(drop=True)
        act_ret = (float(act["close"].iloc[-1]) / float(hist["close"].iloc[-1]) - 1.0) * 100.0
        if abs(act_ret) < 0.05:
            continue
        p_df = pred.predict(
            df=hist[["open", "high", "low", "close", "volume", "amount"]],
            x_timestamp=hist["timestamps"],
            y_timestamp=act["timestamps"],
            pred_len=HORIZON,
            T=0.2,
            top_p=0.9,
            sample_count=5,
            normalization_mode=norm_mode,
            selection_mode="medoid",
        )
        pred_ret = (float(p_df["close"].iloc[-1]) / float(hist["close"].iloc[-1]) - 1.0) * 100.0
        mae = float(np.mean(np.abs(p_df["close"].values - act["close"].values)))
        mape = float(np.mean(np.abs((p_df["close"].values - act["close"].values) / act["close"].values)) * 100.0)
        maes.append(mae)
        mapes.append(mape)
        tot += 1
        if np.sign(pred_ret) == np.sign(act_ret):
            hits += 1
    acc = (hits / max(1, tot)) * 100.0
    return {
        "model": model_name,
        "hits": hits,
        "total": tot,
        "accuracy_pct": round(acc, 1),
        "avg_mae": round(float(np.mean(maes)), 2),
        "avg_mape_pct": round(float(np.mean(mapes)), 2),
    }


def run_confluence_benchmark():
    print("=" * 85)
    print("DUAL-MODEL SPY (23-YR) + VIX COMPANION CONFLUENCE & MULTI-MODEL BENCHMARK")
    print("=" * 85)

    spy_model_dir = ROOT / "finetune_csv" / "finetuned" / "SPY_23yr_multi_tf"
    vix_model_dir = ROOT / "finetune_csv" / "finetuned" / "VIX_companion_multi_tf"

    confluence = SPYVIXConfluencePredictor(
        spy_model_dir=spy_model_dir,
        vix_model_dir=vix_model_dir,
    )

    spot_vix_res = evaluate_confluence_pair(
        confluence,
        ROOT / "data" / "spy_multi_timeframe" / "SPY_1hour_2004_2026.csv",
        ROOT / "data" / "vix_companion" / "INDEX_VIX_1hour_2023_2026.csv",
        "SPY (23-Yr) + Spot VIX (I:VIX) 1-Hour Swing",
    )

    vixy_res = evaluate_confluence_pair(
        confluence,
        ROOT / "data" / "spy_multi_timeframe" / "SPY_1hour_2004_2026.csv",
        ROOT / "data" / "vix_companion" / "VIXY_1hour_2011_2026.csv",
        "SPY (23-Yr) + VIXY ETF 1-Hour Swing",
    )

    print("\n" + "=" * 85)
    print("EVALUATING ALL 23-YEAR MULTI-TIMEFRAME MODELS ON HELD-OUT 2026 WINDOWS (1-HOUR)")
    print("=" * 85)

    suite_configs = [
        ("SPY_23yr_multi_tf", ROOT / "data/spy_multi_timeframe/SPY_1hour_2004_2026.csv", "detrend"),
        ("QQQ_23yr_multi_tf", ROOT / "data/qqq_multi_timeframe/QQQ_1hour_2004_2026.csv", "detrend"),
        ("IWM_23yr_multi_tf", ROOT / "data/iwm_multi_timeframe/IWM_1hour_2004_2026.csv", "detrend"),
        ("GME_23yr_multi_tf", ROOT / "data/gme_multi_timeframe/GME_1hour_2004_2026.csv", "last_price_anchor"),
        ("NVDA_23yr_multi_tf", ROOT / "data/nvda_multi_timeframe/NVDA_1hour_2004_2026.csv", "standard"),
        ("MACRO_TLT_GLD_23yr_multi_tf (GLD)", ROOT / "data/macro_tlt_gld_multi_timeframe/GLD_1hour_2004_2026.csv", "last_price_anchor"),
        ("MACRO_TLT_GLD_23yr_multi_tf (TLT)", ROOT / "data/macro_tlt_gld_multi_timeframe/TLT_1hour_2004_2026.csv", "standard"),
    ]

    suite_results = []
    for label, csv_path, norm_mode in suite_configs:
        model_folder = label.split(" ")[0]
        res = evaluate_single_model(model_folder, csv_path, norm_mode=norm_mode, num_win=25)
        res["label"] = label
        suite_results.append(res)
        print(
            f"  {label:35s} | Accuracy: {res['hits']:2d}/{res['total']:2d} ({res['accuracy_pct']:5.1f}%) "
            f"| Avg MAE: ${res['avg_mae']:6.2f} | MAPE: {res['avg_mape_pct']:.2f}%"
        )

    out_path = OUTPUT_DIR / "confluence_benchmark_summary.json"
    with open(out_path, "w") as f:
        json.dump({
            "confluence_spot_vix": spot_vix_res,
            "confluence_vixy": vixy_res,
            "single_model_suite": suite_results,
        }, f, indent=2)
    print(f"\nSaved full benchmark summary to {out_path}")


if __name__ == "__main__":
    run_confluence_benchmark()
