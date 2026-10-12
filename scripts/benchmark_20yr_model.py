"""
Head-to-Head Out-of-Sample Benchmark:
20-Year Multi-Timeframe Fine-Tuned Kronos vs Original Baseline Kronos
Evaluated across:
1. 5-minute intraday windows (24 bars = 2 hours)
2. 1-hour swing windows (24 bars = 3.5 trading days)
"""
import json
import math
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
import torch

ROOT = Path("/Volumes/MacMoneyMakerSSD/Ai_apps/kronos")
sys.path.insert(0, str(ROOT))
from model import Kronos, KronosTokenizer
from model.enhanced_predictor import EnhancedKronosPredictor
from scripts.research_data_loader import fetch_polygon_bars

OUTPUT_DIR = ROOT / "outputs" / "benchmark_20yr_model"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LOOKBACK = 128
HORIZON = 24
NUM_WINDOWS = 20  # 20 windows per timeframe = 40 total rolling out-of-sample tests

TEST_CONFIGS = [
    {"name": "SPY 5-Min Intraday", "symbol": "SPY", "mult": 5, "span": "minute", "from": "2024-10-01", "to": "2024-11-30"},
    {"name": "SPY 1-Hour Swing", "symbol": "SPY", "mult": 1, "span": "hour", "from": "2024-06-01", "to": "2024-11-30"},
]

def calc_binomial_pval(k, n, p=0.5):
    """Exact one-tailed binomial p-value P(X >= k)."""
    return sum(math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) for i in range(k, n + 1))

def run_benchmark():
    print("=" * 80)
    print("20-YEAR MULTI-TIMEFRAME KRONOS OUT-OF-SAMPLE BENCHMARK")
    print("Comparing Original Baseline vs 20-Year Multi-Timeframe Model")
    print("=" * 80)

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Device: {device}")

    # 1. Baseline Model
    print("Loading Baseline Kronos...")
    base_tok = KronosTokenizer.from_pretrained(str(ROOT / "models" / "Kronos-Tokenizer-base"))
    base_mdl = Kronos.from_pretrained(str(ROOT / "models" / "Kronos-base"))
    base_pred = EnhancedKronosPredictor(base_mdl, base_tok, device=device, max_context=512)

    # 2. 20-Year Multi-Timeframe Model
    print("Loading 20-Year Multi-Timeframe Fine-Tuned Kronos...")
    ft_tok_path = str(ROOT / "finetune_csv" / "finetuned" / "SPY_20yr_multi_timeframe" / "tokenizer" / "best_model")
    ft_mdl_path = str(ROOT / "finetune_csv" / "finetuned" / "SPY_20yr_multi_timeframe" / "basemodel" / "best_model")
    ft_tok = KronosTokenizer.from_pretrained(ft_tok_path)
    ft_mdl = Kronos.from_pretrained(ft_mdl_path)
    ft_pred = EnhancedKronosPredictor(ft_mdl, ft_tok, device=device, max_context=512)

    results = []

    for cfg in TEST_CONFIGS:
        name = cfg["name"]
        sym = cfg["symbol"]
        print(f"\n--- Testing {name} ({NUM_WINDOWS} non-overlapping windows) ---")
        df = fetch_polygon_bars(sym, cfg["mult"], cfg["span"], cfg["from"], cfg["to"])

        base_hits = 0
        ft_hits = 0
        base_maes = []
        ft_maes = []

        for w in range(NUM_WINDOWS, 0, -1):
            end_idx = len(df) - (w * HORIZON)
            hist = df.iloc[:end_idx]
            actual = df.iloc[end_idx : end_idx + HORIZON]

            x = hist.tail(LOOKBACK)
            fut_ts = actual["timestamps"].reset_index(drop=True)
            last_close = float(hist["close"].iloc[-1])
            actual_last = float(actual["close"].iloc[-1])
            actual_ret = (actual_last / last_close - 1) * 100

            # Baseline Prediction
            p_base = base_pred.predict(
                df=x.drop(columns="timestamps"), x_timestamp=x["timestamps"],
                y_timestamp=fut_ts, pred_len=HORIZON, T=0.3, top_p=0.9, sample_count=5,
                normalization_mode="detrend", selection_mode="medoid", verbose=False
            )
            base_last = float(p_base["close"].iloc[-1])
            base_ret = (base_last / last_close - 1) * 100
            b_hit = bool(np.sign(base_ret) == np.sign(actual_ret))
            b_mae = float(np.mean(np.abs(p_base["close"].values - actual["close"].values)))

            # Fine-Tuned 20-Yr Prediction
            p_ft = ft_pred.predict(
                df=x.drop(columns="timestamps"), x_timestamp=x["timestamps"],
                y_timestamp=fut_ts, pred_len=HORIZON, T=0.3, top_p=0.9, sample_count=5,
                normalization_mode="detrend", selection_mode="medoid", verbose=False
            )
            ft_last = float(p_ft["close"].iloc[-1])
            ft_ret = (ft_last / last_close - 1) * 100
            f_hit = bool(np.sign(ft_ret) == np.sign(actual_ret))
            f_mae = float(np.mean(np.abs(p_ft["close"].values - actual["close"].values)))

            if b_hit: base_hits += 1
            if f_hit: ft_hits += 1
            base_maes.append(b_mae)
            ft_maes.append(f_mae)

            results.append({
                "timeframe": name,
                "window": w,
                "timestamp": str(actual["timestamps"].iloc[0]),
                "actual_ret": actual_ret,
                "base_ret": base_ret,
                "base_hit": b_hit,
                "base_mae": b_mae,
                "ft_ret": ft_ret,
                "ft_hit": f_hit,
                "ft_mae": f_mae
            })

            hit_symbol_b = "✓" if b_hit else "✗"
            hit_symbol_f = "✓" if f_hit else "✗"
            print(f"  Win {w:02d} | Actual: {actual_ret:+.2f}% | Base: {base_ret:+.2f}% {hit_symbol_b} (${b_mae:.2f}) | 20yr-FT: {ft_ret:+.2f}% {hit_symbol_f} (${f_mae:.2f})")

        b_acc = (base_hits / NUM_WINDOWS) * 100
        f_acc = (ft_hits / NUM_WINDOWS) * 100
        print(f"\n--> {name} Summary:")
        print(f"    Baseline Accuracy : {base_hits}/{NUM_WINDOWS} ({b_acc:.1f}%), Avg MAE: ${np.mean(base_maes):.2f}")
        print(f"    20-Yr FT Accuracy : {ft_hits}/{NUM_WINDOWS} ({f_acc:.1f}%), Avg MAE: ${np.mean(ft_maes):.2f}")

    # Overall Summary
    total_wins = len(results)
    tot_base_hits = sum(1 for r in results if r["base_hit"])
    tot_ft_hits = sum(1 for r in results if r["ft_hit"])
    tot_base_mae = float(np.mean([r["base_mae"] for r in results]))
    tot_ft_mae = float(np.mean([r["ft_mae"] for r in results]))

    tot_b_acc = (tot_base_hits / total_wins) * 100
    tot_f_acc = (tot_ft_hits / total_wins) * 100

    b_pval = calc_binomial_pval(tot_base_hits, total_wins)
    f_pval = calc_binomial_pval(tot_ft_hits, total_wins)

    print("\n" + "=" * 80)
    print("OVERALL BENCHMARK RESULTS")
    print(f"Total Windows Tested: {total_wins}")
    print(f"Baseline Kronos     : {tot_base_hits}/{total_wins} ({tot_b_acc:.1f}%) | Avg MAE: ${tot_base_mae:.2f} | p-val: {b_pval:.4f}")
    print(f"20-Yr Multi-TF Model: {tot_ft_hits}/{total_wins} ({tot_f_acc:.1f}%) | Avg MAE: ${tot_ft_mae:.2f} | p-val: {f_pval:.4f}")
    print("=" * 80)

    # Save JSON summary
    summary_data = {
        "total_windows": total_wins,
        "baseline": {"hits": tot_base_hits, "accuracy": tot_b_acc, "avg_mae": tot_base_mae, "p_val": b_pval},
        "finetuned_20yr": {"hits": tot_ft_hits, "accuracy": tot_f_acc, "avg_mae": tot_ft_mae, "p_val": f_pval},
        "windows": results
    }
    with open(OUTPUT_DIR / "benchmark_summary.json", "w") as f:
        json.dump(summary_data, f, indent=2)
    print(f"Saved benchmark summary to {OUTPUT_DIR / 'benchmark_summary.json'}")

if __name__ == "__main__":
    run_benchmark()
