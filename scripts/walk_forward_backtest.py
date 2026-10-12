"""
Large-Scale Walk-Forward Backtesting for Kronos Foundation Model.
Evaluates multi-window out-of-sample performance across SPY, QQQ, NVDA, and BTC.
Computes directional hit rates, p-values vs random chance, simulated equity curves,
and high/low volatility envelope coverage.
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

def calc_binomial_pvalue(k, n, p=0.5):
    """Calculate exact one-tailed binomial p-value P(X >= k)."""
    return sum(math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) for i in range(k, n + 1))

def calc_pearson_corr(x, y):
    """Calculate Pearson correlation using numpy."""
    x_arr = np.array(x, dtype=float)
    y_arr = np.array(y, dtype=float)
    x_diff = x_arr - np.mean(x_arr)
    y_diff = y_arr - np.mean(y_arr)
    num = np.sum(x_diff * y_diff)
    den = np.sqrt(np.sum(x_diff ** 2) * np.sum(y_diff ** 2))
    return float(num / den) if den > 0 else 0.0

ROOT = Path("/Volumes/MacMoneyMakerSSD/Ai_apps/kronos")
sys.path.insert(0, str(ROOT))
from model import Kronos, KronosTokenizer, KronosPredictor
from scripts.research_data_loader import fetch_polygon_bars

OUTPUT_DIR = ROOT / "outputs" / "walk_forward"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TICKERS = [
    {"symbol": "SPY", "mult": 1, "span": "day", "type": "stock", "from": "2023-01-01", "to": "2026-10-08"},
    {"symbol": "QQQ", "mult": 1, "span": "day", "type": "stock", "from": "2023-01-01", "to": "2026-10-08"},
    {"symbol": "NVDA", "mult": 1, "span": "day", "type": "stock", "from": "2023-01-01", "to": "2026-10-08"},
    {"symbol": "X:BTCUSD", "mult": 1, "span": "day", "type": "crypto", "from": "2023-01-01", "to": "2026-10-08"}
]

LOOKBACK = 128
PRED_LEN = 10
NUM_WINDOWS = 15  # 15 non-overlapping 10-day windows per asset = 150 days of rolling tests per ticker

def run_walk_forward():
    print("=" * 75)
    print("KRONOS LARGE-SCALE WALK-FORWARD TESTING SUITE")
    print(f"Testing {len(TICKERS)} assets over {NUM_WINDOWS} non-overlapping {PRED_LEN}-day windows each")
    print(f"Total rolling evaluation windows: {len(TICKERS) * NUM_WINDOWS}")
    print("=" * 75)

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Initializing Kronos-base on device: {device}...")
    tokenizer = KronosTokenizer.from_pretrained(str(ROOT / "models" / "Kronos-Tokenizer-base"))
    model = Kronos.from_pretrained(str(ROOT / "models" / "Kronos-base"))
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=512)

    all_results = []
    equity_curves = {}

    for t_info in TICKERS:
        symbol = t_info["symbol"]
        print(f"\n--- Running Walk-Forward on {symbol} ---")
        df = fetch_polygon_bars(symbol, t_info["mult"], t_info["span"], t_info["from"], t_info["to"])
        
        total_bars_needed = LOOKBACK + (NUM_WINDOWS * PRED_LEN)
        if len(df) < total_bars_needed:
            print(f"Warning: {symbol} has {len(df)} bars, needed {total_bars_needed}. Adjusting windows.")
            usable_windows = (len(df) - LOOKBACK) // PRED_LEN
        else:
            usable_windows = NUM_WINDOWS
            
        ticker_equity = [100.0]
        benchmark_equity = [100.0]
        
        # Test windows from oldest to most recent
        for w in range(usable_windows, 0, -1):
            end_idx = len(df) - (w * PRED_LEN)
            hist = df.iloc[:end_idx]
            actual = df.iloc[end_idx : end_idx + PRED_LEN]
            
            x = hist.tail(LOOKBACK)
            fut_ts = actual["timestamps"].reset_index(drop=True)
            last_close = float(hist["close"].iloc[-1])
            start_date_str = str(actual["timestamps"].iloc[0].date())
            end_date_str = str(actual["timestamps"].iloc[-1].date())
            
            # Predict using our calibrated Robust preset (LB=128, T=0.3, S=5)
            preds = predictor.predict(
                df=x.drop(columns="timestamps"),
                x_timestamp=x["timestamps"],
                y_timestamp=fut_ts,
                pred_len=PRED_LEN,
                T=0.3, top_p=0.9, sample_count=5,
                verbose=False
            )
            
            pred_last = float(preds["close"].iloc[-1])
            actual_last = float(actual["close"].iloc[-1])
            pred_return_pct = (pred_last / last_close - 1) * 100
            actual_return_pct = (actual_last / last_close - 1) * 100
            
            dir_hit = bool(np.sign(pred_return_pct) == np.sign(actual_return_pct))
            
            # MAE vs Naive Flat Persistence
            mae = float(np.mean(np.abs(preds["close"].values - actual["close"].values)))
            naive_mae = float(np.mean(np.abs(last_close - actual["close"].values)))
            beats_naive = bool(mae < naive_mae)
            
            # Volatility envelope coverage: did actual prices stay between min(pred_low) and max(pred_high)?
            envelope_low = float(preds["low"].min())
            envelope_high = float(preds["high"].max())
            actual_low = float(actual["low"].min())
            actual_high = float(actual["high"].max())
            inside_envelope = bool(actual_low >= envelope_low and actual_high <= envelope_high)
            
            # Simulated naive strategy: Long if predicted up, Flat (Cash) if predicted down
            strat_return_pct = actual_return_pct if pred_return_pct > 0 else 0.0
            ticker_equity.append(ticker_equity[-1] * (1 + strat_return_pct / 100))
            benchmark_equity.append(benchmark_equity[-1] * (1 + actual_return_pct / 100))
            
            record = {
                "ticker": symbol,
                "window": usable_windows - w + 1,
                "start_date": start_date_str,
                "end_date": end_date_str,
                "last_close": round(last_close, 2),
                "actual_close": round(actual_last, 2),
                "pred_close": round(pred_last, 2),
                "pred_ret_pct": round(pred_return_pct, 2),
                "actual_ret_pct": round(actual_return_pct, 2),
                "dir_hit": dir_hit,
                "mae": round(mae, 2),
                "naive_mae": round(naive_mae, 2),
                "beats_naive": beats_naive,
                "inside_envelope": inside_envelope,
                "envelope_range": f"[{envelope_low:.2f}, {envelope_high:.2f}]",
                "actual_range": f"[{actual_low:.2f}, {actual_high:.2f}]"
            }
            all_results.append(record)
            
            hit_str = "HIT" if dir_hit else "MISS"
            beats_str = "BEATS_NAIVE" if beats_naive else "WORSE"
            print(f"[{symbol:8}] Window {record['window']:2d} ({start_date_str} -> {end_date_str}): Pred={pred_return_pct:+6.2f}% | Actual={actual_return_pct:+6.2f}% [{hit_str:4}] | MAE={mae:5.2f} vs Naive={naive_mae:5.2f} [{beats_str}]")

        equity_curves[symbol] = {
            "strategy": [round(x, 2) for x in ticker_equity],
            "benchmark": [round(x, 2) for x in benchmark_equity]
        }

    # Statistical Aggregation
    df_res = pd.DataFrame(all_results)
    total_tests = len(df_res)
    total_hits = int(df_res["dir_hit"].sum())
    hit_rate_pct = round(total_hits / total_tests * 100, 2)
    
    # Binomial test p-value vs null hypothesis of 50% chance
    binom_pval = calc_binomial_pvalue(total_hits, total_tests, 0.5)
    
    total_beats_naive = int(df_res["beats_naive"].sum())
    beats_naive_pct = round(total_beats_naive / total_tests * 100, 2)
    
    envelope_hits = int(df_res["inside_envelope"].sum())
    envelope_pct = round(envelope_hits / total_tests * 100, 2)
    
    # Correlation between predicted returns and actual returns
    corr = calc_pearson_corr(df_res["pred_ret_pct"], df_res["actual_ret_pct"])
    
    # Per-ticker breakdown
    ticker_breakdowns = {}
    for sym, group in df_res.groupby("ticker"):
        t_total = len(group)
        t_hits = int(group["dir_hit"].sum())
        t_beats = int(group["beats_naive"].sum())
        ticker_breakdowns[sym] = {
            "windows": t_total,
            "hit_rate": f"{t_hits}/{t_total} ({t_hits/t_total*100:.1f}%)",
            "beats_naive": f"{t_beats}/{t_total} ({t_beats/t_total*100:.1f}%)",
            "mean_pred_ret": round(float(group["pred_ret_pct"].mean()), 2),
            "mean_actual_ret": round(float(group["actual_ret_pct"].mean()), 2),
            "strategy_final_equity": equity_curves[sym]["strategy"][-1],
            "benchmark_final_equity": equity_curves[sym]["benchmark"][-1]
        }

    summary = {
        "total_windows": total_tests,
        "overall_dir_hit_rate": f"{total_hits}/{total_tests} ({hit_rate_pct}%)",
        "binomial_p_value_vs_50pct": round(float(binom_pval), 4),
        "statistically_significant_at_5pct": bool(binom_pval < 0.05),
        "overall_beats_naive": f"{total_beats_naive}/{total_tests} ({beats_naive_pct}%)",
        "envelope_coverage": f"{envelope_hits}/{total_tests} ({envelope_pct}%)",
        "return_correlation": round(float(corr), 3),
        "ticker_breakdowns": ticker_breakdowns
    }

    print("\n" + "=" * 75)
    print("WALK-FORWARD STATISTICAL SUMMARY")
    print("=" * 75)
    print(f"Total Forward Windows Tested : {total_tests}")
    print(f"Overall Direction Hit Rate   : {summary['overall_dir_hit_rate']} (p-value: {binom_pval:.4f})")
    print(f"Beats Flat Naive Baseline    : {summary['overall_beats_naive']}")
    print(f"Volatility Envelope Coverage : {summary['envelope_coverage']}")
    print(f"Return Pearson Correlation   : {corr:.3f}")
    print("-" * 75)
    for sym, b in ticker_breakdowns.items():
        print(f"{sym:8} -> Dir Hit: {b['hit_rate']:12} | Beats Naive: {b['beats_naive']:12} | Strat Equity: {b['strategy_final_equity']:6.1f} vs Buy&Hold: {b['benchmark_final_equity']:6.1f}")

    # Generate Equity Curve & Performance Visualization
    fig = make_subplots(rows=2, cols=2, subplot_titles=[f"{s['symbol']} Strategy vs Buy & Hold" for s in TICKERS])
    positions = [(1, 1), (1, 2), (2, 1), (2, 2)]
    
    for idx, t_info in enumerate(TICKERS):
        sym = t_info["symbol"]
        r, c = positions[idx]
        fig.add_trace(go.Scatter(y=equity_curves[sym]["strategy"], mode="lines+markers", name=f"{sym} Kronos Long/Cash", line=dict(color="#00e676")), row=r, col=c)
        fig.add_trace(go.Scatter(y=equity_curves[sym]["benchmark"], mode="lines", name=f"{sym} Buy & Hold", line=dict(color="#2979ff", dash="dash")), row=r, col=c)
        
    fig.update_layout(height=700, template="plotly_dark", title_text="Walk-Forward Strategy Performance (10-Day Horizons)", showlegend=False)
    chart_path = OUTPUT_DIR / "walk_forward_equity_curves.html"
    fig.write_html(str(chart_path))
    print(f"\nEquity curve chart saved to: {chart_path}")

    # Save detailed JSON log
    out_file = OUTPUT_DIR / f"walk_forward_full_results_{pd.Timestamp.now():%Y%m%dT%H%M%S}.json"
    full_output = {
        "summary": summary,
        "equity_curves": equity_curves,
        "window_details": all_results
    }
    out_file.write_text(json.dumps(full_output, indent=2))
    print(f"Full results JSON saved to: {out_file}")

if __name__ == "__main__":
    run_walk_forward()
