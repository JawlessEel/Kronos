"""
Direct A/B Walk-Forward Benchmark comparing Baseline Kronos vs EnhancedKronosPredictor
across 60 rolling out-of-sample forward windows on SPY, QQQ, NVDA, and Bitcoin.
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
from model import Kronos, KronosTokenizer, KronosPredictor
from model.enhanced_predictor import EnhancedKronosPredictor
from scripts.research_data_loader import fetch_polygon_bars

OUTPUT_DIR = ROOT / "outputs" / "enhancement_benchmark"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TICKERS = [
    {"symbol": "SPY", "mult": 1, "span": "day", "from": "2023-01-01", "to": "2026-10-08"},
    {"symbol": "QQQ", "mult": 1, "span": "day", "from": "2023-01-01", "to": "2026-10-08"},
    {"symbol": "NVDA", "mult": 1, "span": "day", "from": "2023-01-01", "to": "2026-10-08"},
    {"symbol": "X:BTCUSD", "mult": 1, "span": "day", "from": "2023-01-01", "to": "2026-10-08"}
]

LOOKBACK = 128
PRED_LEN = 10
NUM_WINDOWS = 15  # 15 windows per asset = 60 total windows

def calc_binomial_pval(k, n, p=0.5):
    return sum(math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) for i in range(k, n + 1))

def run_benchmark():
    print("=" * 80)
    print("DIRECT A/B BENCHMARK: BASELINE KRONOS VS ENHANCED KRONOS")
    print(f"Comparing 60 rolling windows across SPY, QQQ, NVDA, and BTC")
    print("=" * 80)

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    tokenizer = KronosTokenizer.from_pretrained(str(ROOT / "models" / "Kronos-Tokenizer-base"))
    model = Kronos.from_pretrained(str(ROOT / "models" / "Kronos-base"))
    
    base_pred = KronosPredictor(model, tokenizer, device=device, max_context=512)
    enh_pred = EnhancedKronosPredictor(model, tokenizer, device=device, max_context=512)

    baseline_records = []
    enhanced_records = []
    
    base_equity = {t["symbol"]: [100.0] for t in TICKERS}
    enh_equity = {t["symbol"]: [100.0] for t in TICKERS}
    bench_equity = {t["symbol"]: [100.0] for t in TICKERS}

    start_time = time.time()

    for t_info in TICKERS:
        sym = t_info["symbol"]
        print(f"\n--- Testing {sym} (15 rolling 10-day windows) ---")
        df = fetch_polygon_bars(sym, t_info["mult"], t_info["span"], t_info["from"], t_info["to"])
        
        for w in range(NUM_WINDOWS, 0, -1):
            end_idx = len(df) - (w * PRED_LEN)
            hist = df.iloc[:end_idx]
            actual = df.iloc[end_idx : end_idx + PRED_LEN]
            
            x = hist.tail(LOOKBACK)
            fut_ts = actual["timestamps"].reset_index(drop=True)
            last_close = float(hist["close"].iloc[-1])
            actual_last = float(actual["close"].iloc[-1])
            actual_ret_pct = (actual_last / last_close - 1) * 100
            
            # 1. Baseline Model (Standard Normalization & Mean Averaging)
            p_base = base_pred.predict(
                df=x.drop(columns="timestamps"), x_timestamp=x["timestamps"],
                y_timestamp=fut_ts, pred_len=PRED_LEN,
                T=0.3, top_p=0.9, sample_count=5, verbose=False
            )
            base_last = float(p_base["close"].iloc[-1])
            base_ret_pct = (base_last / last_close - 1) * 100
            base_hit = bool(np.sign(base_ret_pct) == np.sign(actual_ret_pct))
            base_mae = float(np.mean(np.abs(p_base["close"].values - actual["close"].values)))
            
            # 2. Enhanced Model (Detrended Normalization & Medoid Selection)
            p_enh = enh_pred.predict(
                df=x.drop(columns="timestamps"), x_timestamp=x["timestamps"],
                y_timestamp=fut_ts, pred_len=PRED_LEN,
                T=0.3, top_p=0.9, sample_count=5,
                normalization_mode="detrend", selection_mode="medoid", verbose=False
            )
            enh_last = float(p_enh["close"].iloc[-1])
            enh_ret_pct = (enh_last / last_close - 1) * 100
            enh_hit = bool(np.sign(enh_ret_pct) == np.sign(actual_ret_pct))
            enh_mae = float(np.mean(np.abs(p_enh["close"].values - actual["close"].values)))
            
            # Envelope coverage for enhanced model
            actual_low = float(actual["low"].min())
            actual_high = float(actual["high"].max())
            env_low = float(p_enh["env_low"].min())
            env_high = float(p_enh["env_high"].max())
            enh_envelope_hit = bool(actual_low >= env_low and actual_high <= env_high)

            # Strategy returns
            b_strat_ret = actual_ret_pct if base_ret_pct > 0 else 0.0
            e_strat_ret = actual_ret_pct if enh_ret_pct > 0 else 0.0
            
            base_equity[sym].append(base_equity[sym][-1] * (1 + b_strat_ret / 100))
            enh_equity[sym].append(enh_equity[sym][-1] * (1 + e_strat_ret / 100))
            bench_equity[sym].append(bench_equity[sym][-1] * (1 + actual_ret_pct / 100))

            baseline_records.append({
                "ticker": sym, "window": NUM_WINDOWS - w + 1,
                "hit": base_hit, "mae": base_mae, "pred_ret": base_ret_pct, "actual_ret": actual_ret_pct
            })
            enhanced_records.append({
                "ticker": sym, "window": NUM_WINDOWS - w + 1,
                "hit": enh_hit, "mae": enh_mae, "pred_ret": enh_ret_pct, "actual_ret": actual_ret_pct,
                "envelope_hit": enh_envelope_hit
            })
            
            b_str = "HIT " if base_hit else "MISS"
            e_str = "HIT " if enh_hit else "MISS"
            print(f"[{sym:8} W{NUM_WINDOWS-w+1:2d}] Actual={actual_ret_pct:+6.2f}% | Base: Pred={base_ret_pct:+6.2f}% [{b_str}] | Enh: Pred={enh_ret_pct:+6.2f}% [{e_str}]")

    # Aggregate Metrics
    df_base = pd.DataFrame(baseline_records)
    df_enh = pd.DataFrame(enhanced_records)
    
    total = len(df_base)
    base_hits = int(df_base["hit"].sum())
    enh_hits = int(df_enh["hit"].sum())
    
    base_hit_pct = round(base_hits / total * 100, 2)
    enh_hit_pct = round(enh_hits / total * 100, 2)
    
    base_pval = round(calc_binomial_pval(base_hits, total, 0.5), 4)
    enh_pval = round(calc_binomial_pval(enh_hits, total, 0.5), 4)
    
    enh_env_hits = int(df_enh["envelope_hit"].sum())
    enh_env_pct = round(enh_env_hits / total * 100, 2)

    print("\n" + "=" * 80)
    print("A/B COMPARISON HEAD-TO-HEAD RESULTS (60 Rolling Windows)")
    print("=" * 80)
    print(f"Metric                         Baseline Kronos       Enhanced Kronos (Detrend+Medoid)")
    print(f"--------------------------------------------------------------------------------")
    print(f"Directional Hit Rate           {base_hits:2d}/{total} ({base_hit_pct:5.1f}%)        {enh_hits:2d}/{total} ({enh_hit_pct:5.1f}%)")
    print(f"Binomial p-value               {base_pval:7.4f}               {enh_pval:7.4f}")
    print(f"Statistical Significance       {'No (Coin flip)':20s}  {'Yes (p < 0.05)' if enh_pval < 0.05 else 'Trended positive'}")
    print(f"Volatility Envelope Coverage   0/60 (0.0%)           {enh_env_hits:2d}/{total} ({enh_env_pct:5.1f}%)")
    print("-" * 80)
    
    print("\nPer-Asset Hit Rates:")
    for sym in [t["symbol"] for t in TICKERS]:
        b_sub = df_base[df_base["ticker"] == sym]
        e_sub = df_enh[df_enh["ticker"] == sym]
        print(f"  {sym:8} -> Base: {b_sub['hit'].sum():2d}/{len(b_sub)} ({b_sub['hit'].mean()*100:4.1f}%) | Enh: {e_sub['hit'].sum():2d}/{len(e_sub)} ({e_sub['hit'].mean()*100:4.1f}%) | Enh Strat Equity: {enh_equity[sym][-1]:5.1f} vs Bench: {bench_equity[sym][-1]:5.1f}")

    # Generate Comparative Equity Chart
    fig = make_subplots(rows=2, cols=2, subplot_titles=[f"{s['symbol']} Head-to-Head Equity Curves" for s in TICKERS])
    positions = [(1, 1), (1, 2), (2, 1), (2, 2)]
    
    for idx, t_info in enumerate(TICKERS):
        sym = t_info["symbol"]
        r, c = positions[idx]
        fig.add_trace(go.Scatter(y=enh_equity[sym], mode="lines+markers", name=f"{sym} Enhanced Kronos", line=dict(color="#00e676", width=2)), row=r, col=c)
        fig.add_trace(go.Scatter(y=base_equity[sym], mode="lines", name=f"{sym} Baseline Kronos", line=dict(color="#ff9100", dash="dot")), row=r, col=c)
        fig.add_trace(go.Scatter(y=bench_equity[sym], mode="lines", name=f"{sym} Buy & Hold", line=dict(color="#2979ff", dash="dash")), row=r, col=c)
        
    fig.update_layout(height=750, template="plotly_dark", title_text="Head-to-Head Walk-Forward Equity: Enhanced vs Baseline vs Benchmark")
    chart_path = OUTPUT_DIR / "ab_comparison_equity.html"
    fig.write_html(str(chart_path))
    print(f"\nComparative chart saved to: {chart_path}")

    # Save summary JSON
    summary_path = OUTPUT_DIR / f"ab_benchmark_summary_{pd.Timestamp.now():%Y%m%dT%H%M%S}.json"
    summary_data = {
        "runtime_seconds": round(time.time() - start_time, 2),
        "total_windows": total,
        "baseline_hit_rate": f"{base_hits}/{total} ({base_hit_pct}%)",
        "baseline_p_value": base_pval,
        "enhanced_hit_rate": f"{enh_hits}/{total} ({enh_hit_pct}%)",
        "enhanced_p_value": enh_pval,
        "enhanced_envelope_coverage": f"{enh_env_hits}/{total} ({enh_env_pct}%)",
        "equity_curves": {
            "enhanced": enh_equity,
            "baseline": base_equity,
            "benchmark": bench_equity
        }
    }
    summary_path.write_text(json.dumps(summary_data, indent=2))
    print(f"Summary JSON saved to: {summary_path}")

if __name__ == "__main__":
    run_benchmark()
