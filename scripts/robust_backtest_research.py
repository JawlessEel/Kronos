"""
Robust Multi-Asset, Multi-Season, Multi-Timeframe Kronos Backtesting & Hyperparameter Tuning.
Designed to minimize overfitting risk via out-of-sample holdout validation and cross-regime testing.
"""
import itertools
import json
import os
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
from scripts.research_data_loader import fetch_polygon_bars

OUTPUT_DIR = ROOT / "outputs" / "research"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Define diverse test scenarios across underlying assets, timeframes, and seasons
SCENARIOS = {
    # IN-SAMPLE TUNING REGIMES
    "tuning": [
        {
            "id": "SPY_D_Spring24",
            "name": "SPY Daily (Spring 2024 Bull Trend)",
            "ticker": "SPY",
            "timeframe": "1d",
            "multiplier": 1,
            "timespan": "day",
            "fetch_start": "2023-01-01",
            "fetch_end": "2024-05-15",
            "cutoff_date": "2024-03-28",
            "pred_len": 10
        },
        {
            "id": "QQQ_D_Summer24",
            "name": "QQQ Daily (Summer 2024 Tech Correction)",
            "ticker": "QQQ",
            "timeframe": "1d",
            "multiplier": 1,
            "timespan": "day",
            "fetch_start": "2023-06-01",
            "fetch_end": "2024-09-15",
            "cutoff_date": "2024-07-16",
            "pred_len": 10
        },
        {
            "id": "NVDA_1H_Summer24",
            "name": "NVDA 1-Hour (Summer 2024 Volatility Swings)",
            "ticker": "NVDA",
            "timeframe": "1h",
            "multiplier": 1,
            "timespan": "hour",
            "fetch_start": "2024-04-01",
            "fetch_end": "2024-08-01",
            "cutoff_date": "2024-06-25",
            "pred_len": 12
        },
        {
            "id": "BTC_D_Spring24",
            "name": "BTC Daily (Spring 2024 Halving Consolidation)",
            "ticker": "X:BTCUSD",
            "timeframe": "1d",
            "multiplier": 1,
            "timespan": "day",
            "fetch_start": "2023-01-01",
            "fetch_end": "2024-06-15",
            "cutoff_date": "2024-04-12",
            "pred_len": 10
        }
    ],
    # STRICT OUT-OF-SAMPLE HOLDOUT VALIDATION REGIMES
    "holdout": [
        {
            "id": "SPY_1H_Autumn24",
            "name": "SPY 1-Hour (Autumn 2024 Intraday Momentum)",
            "ticker": "SPY",
            "timeframe": "1h",
            "multiplier": 1,
            "timespan": "hour",
            "fetch_start": "2024-07-01",
            "fetch_end": "2024-11-01",
            "cutoff_date": "2024-09-23",
            "pred_len": 12
        },
        {
            "id": "QQQ_D_Winter24",
            "name": "QQQ Daily (Winter 2024 Year-End Rally)",
            "ticker": "QQQ",
            "timeframe": "1d",
            "multiplier": 1,
            "timespan": "day",
            "fetch_start": "2023-06-01",
            "fetch_end": "2024-12-31",
            "cutoff_date": "2024-11-06",
            "pred_len": 10
        },
        {
            "id": "BTC_1H_Autumn24",
            "name": "BTC 1-Hour (Autumn 2024 Crypto Breakout)",
            "ticker": "X:BTCUSD",
            "timeframe": "1h",
            "multiplier": 1,
            "timespan": "hour",
            "fetch_start": "2024-08-01",
            "fetch_end": "2024-11-30",
            "cutoff_date": "2024-10-18",
            "pred_len": 12
        }
    ]
}

def load_scenario_data(scenario):
    """Load and prepare input history and ground-truth future."""
    df = fetch_polygon_bars(
        scenario["ticker"], scenario["multiplier"], scenario["timespan"],
        scenario["fetch_start"], scenario["fetch_end"]
    )
    cutoff_dt = pd.to_datetime(scenario["cutoff_date"], utc=True)
    hist_mask = df["timestamps"] <= cutoff_dt
    hist_df = df[hist_mask].copy()
    actual_df = df[~hist_mask].head(scenario["pred_len"]).copy()
    
    if len(actual_df) < scenario["pred_len"]:
        raise ValueError(f"Scenario {scenario['id']} has insufficient future bars ({len(actual_df)} < {scenario['pred_len']})")
    return hist_df, actual_df

def evaluate_prediction(preds, actual_df, last_close):
    """Calculate error metrics normalized by asset price."""
    pred_closes = preds["close"].values
    actual_closes = actual_df["close"].values
    
    # Normalized MAE in percent
    mae_pct = np.mean(np.abs(pred_closes - actual_closes)) / last_close * 100
    rmse_pct = np.sqrt(np.mean((pred_closes - actual_closes) ** 2)) / last_close * 100
    
    # Naive baseline (persistence: assumes price stays flat at last_close)
    naive_mae_pct = np.mean(np.abs(last_close - actual_closes)) / last_close * 100
    beats_naive = bool(mae_pct < naive_mae_pct)
    
    # Directional hit
    pred_dir = np.sign(pred_closes[-1] - last_close)
    actual_dir = np.sign(actual_closes[-1] - last_close)
    dir_hit = bool(pred_dir == actual_dir)
    
    return {
        "mae_pct": round(float(mae_pct), 3),
        "rmse_pct": round(float(rmse_pct), 3),
        "naive_mae_pct": round(float(naive_mae_pct), 3),
        "beats_naive": beats_naive,
        "dir_hit": dir_hit,
        "pred_return_pct": round(float((pred_closes[-1] / last_close - 1) * 100), 2),
        "actual_return_pct": round(float((actual_closes[-1] / last_close - 1) * 100), 2)
    }

def run_research():
    print("=" * 70)
    print("KRONOS MULTI-REGIME / MULTI-TIMEFRAME RESEARCH SUITE")
    print("Mitigating Overfitting with Cross-Regime & Holdout Validation")
    print("=" * 70)
    
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Loading Kronos-base on device: {device}...")
    tokenizer = KronosTokenizer.from_pretrained(str(ROOT / "models" / "Kronos-Tokenizer-base"))
    model = Kronos.from_pretrained(str(ROOT / "models" / "Kronos-base"))
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=512)
    
    # 1. Preload scenario data
    scenario_data = {}
    for group in ("tuning", "holdout"):
        for sc in SCENARIOS[group]:
            hist_df, actual_df = load_scenario_data(sc)
            scenario_data[sc["id"]] = {"hist": hist_df, "actual": actual_df, "config": sc}
            print(f"Loaded {sc['name']}: {len(hist_df)} history bars, {len(actual_df)} future bars.")

    # 2. Define Parameter Grid
    grid = {
        "lookback": [64, 128, 256],
        "temperature": [0.3, 0.7, 1.0],
        "sample_count": [1, 5]
    }
    combinations = list(itertools.product(grid["lookback"], grid["temperature"], grid["sample_count"]))
    print(f"\n--- Phase 1: In-Sample Hyperparameter Tuning ({len(combinations)} configurations across 4 regimes) ---")
    
    tuning_results = []
    start_time = time.time()
    
    for idx, (lb, temp, samples) in enumerate(combinations):
        cfg_key = f"LB{lb}_T{temp}_S{samples}"
        regime_metrics = []
        
        for sc in SCENARIOS["tuning"]:
            data = scenario_data[sc["id"]]
            hist = data["hist"]
            actual = data["actual"]
            
            x = hist.tail(lb)
            last_close = float(hist["close"].iloc[-1])
            fut_ts = actual["timestamps"].reset_index(drop=True)
            
            preds = predictor.predict(
                df=x.drop(columns="timestamps"),
                x_timestamp=x["timestamps"],
                y_timestamp=fut_ts,
                pred_len=sc["pred_len"],
                T=temp,
                top_p=0.9,
                sample_count=samples,
                verbose=False
            )
            
            m = evaluate_prediction(preds, actual, last_close)
            regime_metrics.append(m)
            
        avg_mae_pct = np.mean([m["mae_pct"] for m in regime_metrics])
        hit_rate = np.mean([m["dir_hit"] for m in regime_metrics])
        beats_naive_rate = np.mean([m["beats_naive"] for m in regime_metrics])
        
        tuning_results.append({
            "config_id": cfg_key,
            "lookback": lb,
            "temperature": temp,
            "sample_count": samples,
            "avg_mae_pct": round(float(avg_mae_pct), 3),
            "dir_hit_rate": round(float(hit_rate * 100), 1),
            "beats_naive_rate": round(float(beats_naive_rate * 100), 1),
            "regime_details": regime_metrics
        })
        print(f"[{idx+1}/{len(combinations)}] {cfg_key:18} -> Avg MAE: {avg_mae_pct:5.2f}% | Direction: {hit_rate*100:4.1f}% | Beats Naive: {beats_naive_rate*100:4.1f}%")

    # Sort tuning results by lowest normalized MAE
    ranked_tuning = sorted(tuning_results, key=lambda x: x["avg_mae_pct"])
    top_3_configs = ranked_tuning[:3]
    
    print("\n" + "=" * 70)
    print("PHASE 1 TUNING LEADERBOARD (Top 3 In-Sample Configurations)")
    print("=" * 70)
    for rank, cfg in enumerate(top_3_configs, 1):
        print(f"Rank {rank}: {cfg['config_id']} | Avg MAE: {cfg['avg_mae_pct']}% | Dir Hit: {cfg['dir_hit_rate']}% | Beats Naive: {cfg['beats_naive_rate']}%")

    # 3. Phase 2: Out-of-Sample Holdout Validation
    print("\n" + "=" * 70)
    print("PHASE 2: OUT-OF-SAMPLE HOLDOUT VALIDATION (Testing for Overfitting)")
    print("Evaluating Top 3 on Unseen Assets / Timeframes / Seasons")
    print("=" * 70)
    
    holdout_evaluations = []
    best_preds_for_charts = {}
    
    for cfg in top_3_configs:
        lb = cfg["lookback"]
        temp = cfg["temperature"]
        samples = cfg["sample_count"]
        cfg_key = cfg["config_id"]
        
        holdout_metrics = []
        for sc in SCENARIOS["holdout"]:
            data = scenario_data[sc["id"]]
            hist = data["hist"]
            actual = data["actual"]
            
            x = hist.tail(lb)
            last_close = float(hist["close"].iloc[-1])
            fut_ts = actual["timestamps"].reset_index(drop=True)
            
            preds = predictor.predict(
                df=x.drop(columns="timestamps"),
                x_timestamp=x["timestamps"],
                y_timestamp=fut_ts,
                pred_len=sc["pred_len"],
                T=temp,
                top_p=0.9,
                sample_count=samples,
                verbose=False
            )
            
            m = evaluate_prediction(preds, actual, last_close)
            holdout_metrics.append(m)
            
            # Store preds of rank 1 config for charting
            if cfg == top_3_configs[0]:
                best_preds_for_charts[sc["id"]] = preds
                
        avg_holdout_mae = np.mean([m["mae_pct"] for m in holdout_metrics])
        holdout_hit_rate = np.mean([m["dir_hit"] for m in holdout_metrics])
        holdout_beats_naive = np.mean([m["beats_naive"] for m in holdout_metrics])
        
        # Overfitting Degradation Ratio: Holdout MAE / Tuning MAE
        overfit_ratio = avg_holdout_mae / cfg["avg_mae_pct"]
        
        holdout_evaluations.append({
            "config_id": cfg_key,
            "lookback": lb,
            "temperature": temp,
            "sample_count": samples,
            "tuning_mae_pct": cfg["avg_mae_pct"],
            "holdout_mae_pct": round(float(avg_holdout_mae), 3),
            "holdout_dir_hit_rate": round(float(holdout_hit_rate * 100), 1),
            "holdout_beats_naive": round(float(holdout_beats_naive * 100), 1),
            "overfit_ratio": round(float(overfit_ratio), 2),
            "verdict": "Robust / Generalizes" if overfit_ratio <= 1.25 else "Overfit / Regressed"
        })
        
        print(f"{cfg_key:18} -> Holdout MAE: {avg_holdout_mae:5.2f}% | Dir Hit: {holdout_hit_rate*100:4.1f}% | Beats Naive: {holdout_beats_naive*100:4.1f}% | Overfit Ratio: {overfit_ratio:.2f} ({holdout_evaluations[-1]['verdict']})")

    # 4. Generate Interactive Multi-Regime HTML Charts
    print("\nGenerating interactive research charts...")
    chart_files = create_research_charts(scenario_data, best_preds_for_charts, top_3_configs[0]["config_id"])
    
    # 5. Save Comprehensive Experiment Results
    experiment_summary = {
        "device": device,
        "runtime_seconds": round(time.time() - start_time, 2),
        "tuning_leaderboard": ranked_tuning,
        "holdout_validation": holdout_evaluations,
        "best_overall_config": holdout_evaluations[0],
        "chart_files": chart_files
    }
    
    summary_path = OUTPUT_DIR / f"robust_backtest_summary_{pd.Timestamp.now():%Y%m%dT%H%M%S}.json"
    summary_path.write_text(json.dumps(experiment_summary, indent=2))
    print(f"\nAll research data and charts successfully saved to {OUTPUT_DIR}")
    return experiment_summary

def create_research_charts(scenario_data, best_preds, best_cfg_id):
    """Generate Plotly interactive charts for holdout scenarios comparing History, Actual, and Prediction."""
    generated_charts = []
    
    for sc in SCENARIOS["holdout"]:
        sc_id = sc["id"]
        if sc_id not in best_preds:
            continue
            
        data = scenario_data[sc_id]
        hist = data["hist"].tail(80)  # show last 80 bars for visual clarity
        actual = data["actual"]
        preds = best_preds[sc_id]
        
        fig = go.Figure()
        
        # Historical context
        fig.add_trace(go.Candlestick(
            x=hist["timestamps"],
            open=hist["open"], high=hist["high"], low=hist["low"], close=hist["close"],
            name="History (Conditioning Input)",
            increasing_line_color="#26a69a", decreasing_line_color="#ef5350"
        ))
        
        # Ground-truth future
        fig.add_trace(go.Candlestick(
            x=actual["timestamps"],
            open=actual["open"], high=actual["high"], low=actual["low"], close=actual["close"],
            name="Actual Future (Ground Truth)",
            increasing_line_color="#2962ff", decreasing_line_color="#d50000"
        ))
        
        # Kronos forecast
        fig.add_trace(go.Candlestick(
            x=actual["timestamps"],
            open=preds["open"], high=preds["high"], low=preds["low"], close=preds["close"],
            name=f"Kronos Forecast ({best_cfg_id})",
            increasing_line_color="#e040fb", decreasing_line_color="#7c4dff"
        ))
        
        fig.update_layout(
            title=f"Holdout Test: {sc['name']} | Actual vs Predicted ({best_cfg_id})",
            xaxis_title="Timestamp",
            yaxis_title="Price (USD)",
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            height=600,
            legend=dict(orientation="h", y=1.08)
        )
        
        chart_file = OUTPUT_DIR / f"chart_{sc_id}.html"
        fig.write_html(str(chart_file))
        generated_charts.append(str(chart_file))
        
    return generated_charts

if __name__ == "__main__":
    run_research()
