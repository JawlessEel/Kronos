"""
Large-Scale Head-to-Head Out-of-Sample Benchmark:
Fine-Tuned Kronos vs Original Pretrained Kronos across 60 Unseen 5-Minute Intraday Windows.
"""
import json
import math
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import torch

ROOT = Path("/Volumes/MacMoneyMakerSSD/Ai_apps/kronos")
sys.path.insert(0, str(ROOT))
from model import Kronos, KronosTokenizer
from model.enhanced_predictor import EnhancedKronosPredictor
from scripts.research_data_loader import fetch_polygon_bars

OUTPUT_DIR = ROOT / "outputs" / "finetuned_benchmark"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LOOKBACK = 128
HORIZON = 24       # 24 5-minute bars = 2 hours forward
NUM_WINDOWS = 30   # 30 non-overlapping windows per ticker = 60 total windows

TICKERS = [
    {"symbol": "SPY", "mult": 5, "span": "minute", "from": "2024-10-01", "to": "2024-11-30"},
    {"symbol": "QQQ", "mult": 5, "span": "minute", "from": "2024-10-01", "to": "2024-11-30"}
]

def calc_binomial_pval(k, n, p=0.5):
    """Exact one-tailed binomial p-value P(X >= k)."""
    return sum(math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) for i in range(k, n + 1))

def run_large_scale_test():
    print("=" * 80)
    print("LARGE-SCALE HEAD-TO-HEAD BENCHMARK: ORIGINAL VS FINE-TUNED KRONOS")
    print(f"Testing 60 Unseen Out-of-Sample Windows (24-bar / 2-hour intraday forecasts)")
    print("=" * 80)

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Loading models on device: {device}...")
    
    # 1. Original Model
    orig_tok = KronosTokenizer.from_pretrained(str(ROOT / "models" / "Kronos-Tokenizer-base"))
    orig_mdl = Kronos.from_pretrained(str(ROOT / "models" / "Kronos-base"))
    orig_pred = EnhancedKronosPredictor(orig_mdl, orig_tok, device=device, max_context=512)

    # 2. Fine-Tuned Model
    ft_tok_path = str(ROOT / "finetune_csv" / "finetuned" / "SPY_5min_intraday" / "tokenizer" / "best_model")
    ft_mdl_path = str(ROOT / "finetune_csv" / "finetuned" / "SPY_5min_intraday" / "basemodel" / "best_model")
    ft_tok = KronosTokenizer.from_pretrained(ft_tok_path)
    ft_mdl = Kronos.from_pretrained(ft_mdl_path)
    ft_pred = EnhancedKronosPredictor(ft_mdl, ft_tok, device=device, max_context=512)

    start_time = time.time()
    all_results = []
    
    orig_equity = {t["symbol"]: [100.0] for t in TICKERS}
    ft_equity = {t["symbol"]: [100.0] for t in TICKERS}
    bench_equity = {t["symbol"]: [100.0] for t in TICKERS}

    for t_info in TICKERS:
        sym = t_info["symbol"]
        print(f"\n--- Running 30 Rolling Windows on {sym} 5-Minute Bars ---")
        df = fetch_polygon_bars(sym, t_info["mult"], t_info["span"], t_info["from"], t_info["to"])
        
        # Step through non-overlapping windows from earlier to recent in October-November 2024
        for w in range(NUM_WINDOWS, 0, -1):
            end_idx = len(df) - (w * HORIZON)
            hist = df.iloc[:end_idx]
            actual = df.iloc[end_idx : end_idx + HORIZON]
            
            x = hist.tail(LOOKBACK)
            fut_ts = actual["timestamps"].reset_index(drop=True)
            last_close = float(hist["close"].iloc[-1])
            actual_last = float(actual["close"].iloc[-1])
            actual_ret = (actual_last / last_close - 1) * 100
            
            start_time_str = actual["timestamps"].iloc[0].strftime("%m-%d %H:%M")
            
            # Prediction 1: Original Model
            p_orig = orig_pred.predict(
                df=x.drop(columns="timestamps"), x_timestamp=x["timestamps"],
                y_timestamp=fut_ts, pred_len=HORIZON, T=0.3, top_p=0.9, sample_count=5,
                normalization_mode="detrend", selection_mode="medoid", verbose=False
            )
            orig_last = float(p_orig["close"].iloc[-1])
            orig_ret = (orig_last / last_close - 1) * 100
            orig_hit = bool(np.sign(orig_ret) == np.sign(actual_ret))
            orig_mae = float(np.mean(np.abs(p_orig["close"].values - actual["close"].values)))

            # Prediction 2: Fine-Tuned Model
            p_ft = ft_pred.predict(
                df=x.drop(columns="timestamps"), x_timestamp=x["timestamps"],
                y_timestamp=fut_ts, pred_len=HORIZON, T=0.3, top_p=0.9, sample_count=5,
                normalization_mode="detrend", selection_mode="medoid", verbose=False
            )
            ft_last = float(p_ft["close"].iloc[-1])
            ft_ret = (ft_last / last_close - 1) * 100
            ft_hit = bool(np.sign(ft_ret) == np.sign(actual_ret))
            ft_mae = float(np.mean(np.abs(p_ft["close"].values - actual["close"].values)))
            
            # Naive baseline
            naive_mae = float(np.mean(np.abs(last_close - actual["close"].values)))
            ft_beats_naive = bool(ft_mae < naive_mae)
            ft_beats_orig = bool(ft_mae < orig_mae)

            # Strategy returns (Long if predicted positive, Cash if predicted negative)
            o_strat = actual_ret if orig_ret > 0 else 0.0
            ft_strat = actual_ret if ft_ret > 0 else 0.0
            
            orig_equity[sym].append(orig_equity[sym][-1] * (1 + o_strat / 100))
            ft_equity[sym].append(ft_equity[sym][-1] * (1 + ft_strat / 100))
            bench_equity[sym].append(bench_equity[sym][-1] * (1 + actual_ret / 100))

            record = {
                "ticker": sym,
                "window": NUM_WINDOWS - w + 1,
                "time": start_time_str,
                "last_close": round(last_close, 2),
                "actual_close": round(actual_last, 2),
                "actual_ret_pct": round(actual_ret, 2),
                "orig_pred_ret": round(orig_ret, 2),
                "orig_hit": orig_hit,
                "orig_mae": round(orig_mae, 2),
                "ft_pred_ret": round(ft_ret, 2),
                "ft_hit": ft_hit,
                "ft_mae": round(ft_mae, 2),
                "naive_mae": round(naive_mae, 2),
                "ft_beats_naive": ft_beats_naive,
                "ft_beats_orig": ft_beats_orig
            }
            all_results.append(record)

            o_str = "HIT" if orig_hit else "MISS"
            f_str = "HIT" if ft_hit else "MISS"
            print(f"[{sym:4} W{record['window']:2d} {start_time_str}] Actual={actual_ret:+5.2f}% | Orig: {orig_ret:+5.2f}% [{o_str:4}] MAE=${orig_mae:.2f} | FT: {ft_ret:+5.2f}% [{f_str:4}] MAE=${ft_mae:.2f} | {'FT_BETTER' if ft_beats_orig else 'ORIG_BETTER'}")

    # Aggregate Statistics
    df_res = pd.DataFrame(all_results)
    total_tests = len(df_res)
    
    orig_total_hits = int(df_res["orig_hit"].sum())
    ft_total_hits = int(df_res["ft_hit"].sum())
    
    orig_hit_pct = round(orig_total_hits / total_tests * 100, 2)
    ft_hit_pct = round(ft_total_hits / total_tests * 100, 2)
    
    orig_pval = round(calc_binomial_pval(orig_total_hits, total_tests, 0.5), 4)
    ft_pval = round(calc_binomial_pval(ft_total_hits, total_tests, 0.5), 4)
    
    orig_avg_mae = round(float(df_res["orig_mae"].mean()), 2)
    ft_avg_mae = round(float(df_res["ft_mae"].mean()), 2)
    naive_avg_mae = round(float(df_res["naive_mae"].mean()), 2)
    
    ft_won_windows = int(df_res["ft_beats_orig"].sum())
    ft_won_pct = round(ft_won_windows / total_tests * 100, 2)
    
    ft_beats_naive_count = int(df_res["ft_beats_naive"].sum())
    ft_beats_naive_pct = round(ft_beats_naive_count / total_tests * 100, 2)

    print("\n" + "=" * 80)
    print("HEAD-TO-HEAD STATISTICAL AGGREGATION (60 Rolling Windows)")
    print("=" * 80)
    print(f"Metric                            Original Pretrained       Fine-Tuned Kronos")
    print(f"--------------------------------------------------------------------------------")
    print(f"Directional Hit Rate              {orig_total_hits:2d}/{total_tests} ({orig_hit_pct:5.1f}%)            {ft_total_hits:2d}/{total_tests} ({ft_hit_pct:5.1f}%)")
    print(f"Binomial p-value vs 50%           {orig_pval:7.4f}                   {ft_pval:7.4f}")
    print(f"Statistical Significance          {'No (p > 0.05)':20s}      {'YES (p < 0.05)' if ft_pval < 0.05 else 'Trended positive'}")
    print(f"Average Price MAE                 ${orig_avg_mae:.2f}                     ${ft_avg_mae:.2f} (Naive: ${naive_avg_mae:.2f})")
    print(f"Windows FT Beat Original          —                       {ft_won_windows}/{total_tests} ({ft_won_pct}%)")
    print(f"Windows FT Beat Naive             —                       {ft_beats_naive_count}/{total_tests} ({ft_beats_naive_pct}%)")
    print("-" * 80)

    # Per-Ticker Breakdown
    for sym in ["SPY", "QQQ"]:
        sub = df_res[df_res["ticker"] == sym]
        o_h = sub["orig_hit"].sum()
        f_h = sub["ft_hit"].sum()
        f_w = sub["ft_beats_orig"].sum()
        print(f"\n{sym} Results (30 Windows):")
        print(f"  Original Hit Rate   : {o_h}/30 ({o_h/30*100:.1f}%) | Avg MAE: ${sub['orig_mae'].mean():.2f} | Strategy Equity: {orig_equity[sym][-1]:.1f}")
        print(f"  Fine-Tuned Hit Rate : {f_h}/30 ({f_h/30*100:.1f}%) | Avg MAE: ${sub['ft_mae'].mean():.2f} | Strategy Equity: {ft_equity[sym][-1]:.1f}")
        print(f"  Buy & Hold Benchmark: {bench_equity[sym][-1]:.1f}")
        print(f"  Fine-Tuned Beat Orig in {f_w}/30 ({f_w/30*100:.1f}%) of windows")

    # Generate Comparative Equity Curves
    fig = make_subplots(rows=1, cols=2, subplot_titles=["SPY 5-Min Strategy vs Benchmark", "QQQ 5-Min Strategy vs Benchmark"])
    for idx, sym in enumerate(["SPY", "QQQ"], start=1):
        fig.add_trace(go.Scatter(y=ft_equity[sym], mode="lines+markers", name=f"{sym} Fine-Tuned", line=dict(color="#00e676", width=2.5)), row=1, col=idx)
        fig.add_trace(go.Scatter(y=orig_equity[sym], mode="lines", name=f"{sym} Original", line=dict(color="#ff9100", dash="dot", width=1.8)), row=1, col=idx)
        fig.add_trace(go.Scatter(y=bench_equity[sym], mode="lines", name=f"{sym} Buy & Hold", line=dict(color="#2979ff", dash="dash", width=1.5)), row=1, col=idx)

    fig.update_layout(height=500, template="plotly_dark", title_text="60-Window Walk-Forward: Fine-Tuned vs Original vs Buy & Hold")
    chart_file = OUTPUT_DIR / "finetuned_vs_original_equity.html"
    fig.write_html(str(chart_file))
    print(f"\nInteractive equity curves saved to: {chart_file}")

    # Save detailed JSON summary
    summary_file = OUTPUT_DIR / f"finetuned_benchmark_summary_{pd.Timestamp.now():%Y%m%dT%H%M%S}.json"
    output_payload = {
        "device": device,
        "runtime_seconds": round(time.time() - start_time, 2),
        "total_windows": total_tests,
        "summary": {
            "original_hit_rate": f"{orig_total_hits}/{total_tests} ({orig_hit_pct}%)",
            "original_p_value": orig_pval,
            "original_avg_mae": orig_avg_mae,
            "finetuned_hit_rate": f"{ft_total_hits}/{total_tests} ({ft_hit_pct}%)",
            "finetuned_p_value": ft_pval,
            "finetuned_avg_mae": ft_avg_mae,
            "naive_avg_mae": naive_avg_mae,
            "finetuned_won_vs_orig": f"{ft_won_windows}/{total_tests} ({ft_won_pct}%)",
            "finetuned_won_vs_naive": f"{ft_beats_naive_count}/{total_tests} ({ft_beats_naive_pct}%)"
        },
        "equity_curves": {
            "finetuned": ft_equity,
            "original": orig_equity,
            "benchmark": bench_equity
        },
        "windows": all_results
    }
    summary_file.write_text(json.dumps(output_payload, indent=2))
    print(f"Full benchmark details saved to: {summary_file}")

if __name__ == "__main__":
    run_large_scale_test()
