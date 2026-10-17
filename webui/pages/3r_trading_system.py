"""
Dedicated 3R Rule Structural Trading System Page & Analytical Dashboard for Kronos WebUI.

Merges Kronos foundation model candlestick forecasting with Doug's 3R Rule Trading System:
- Multi-timeframe dual-chart analysis (View 1: Daily 1D Macro 50-SMA & 14-ATR; View 2: Intraday 5M Execution & 4 Liquidity Levels)
- Confluence Screener & Target Feasibility Gate (Trends, Liquidity Zones, ATR Budget, Candle Compression)
- Anti-Pattern Detection (Chased Breakout Trap & ATR Exhaustion Overextension)
- Structural Stop-Loss & Risk Position Sizing Calculator ($20–$50 fixed risk unit)
- "The Wall Street Raise" 10% Account Scaling Matrix & Consistency Tracker
"""
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import threading
import time
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from plotly.utils import PlotlyJSONEncoder
from flask import Blueprint, jsonify, render_template, request
import torch

from webui.polygon_feed import FeedError
from webui.services.structural_analysis import MarketStructure, StructuralAnalyzer
from webui.services.confluence_engine import (
    ConfluenceEvaluation,
    evaluate_forecast_confluence,
    generate_and_evaluate_forecast,
)
from webui.services.sizing_calculator import (
    calculate_trade_sizing,
    calculate_wall_street_raise_ladder,
    evaluate_scaling_eligibility,
)
from webui.testing_suite import (
    DATA_DIR,
    TICKER_TO_MODEL_MAP,
    TUNED_MODEL_CATALOG,
    resolve_local_dataset_csv,
)

ROOT = Path(__file__).resolve().parents[2]

RECOMMENDED_3R_ASSETS: List[Dict[str, Any]] = [
    {
        "symbol": "SPY",
        "name": "SPDR S&P 500 ETF Trust (ES / MES Proxy)",
        "category": "Index Proxy / Tuned 23-Yr",
        "point_multiplier": 1.0,
        "model_key": "SPY_23yr_multi_tf",
        "notes": "Upward macroeconomic drift (~80% multi-session advance rate); primary 3R index proxy.",
    },
    {
        "symbol": "QQQ",
        "name": "Invesco QQQ Trust (NQ / MNQ Proxy)",
        "category": "Index Proxy / Tuned 23-Yr",
        "point_multiplier": 1.0,
        "model_key": "QQQ_23yr_multi_tf",
        "notes": "Nasdaq-100 structural momentum & clean 5M liquidity boundaries.",
    },
    {
        "symbol": "IWM",
        "name": "iShares Russell 2000 ETF (RTY / M2K Proxy)",
        "category": "Index Proxy / Tuned 23-Yr",
        "point_multiplier": 1.0,
        "model_key": "IWM_23yr_multi_tf",
        "notes": "Small-cap index proxy with well-defined Range High / Range Low mean reversion.",
    },
    {
        "symbol": "NVDA",
        "name": "NVIDIA Corp (Single-Stock Momentum)",
        "category": "Single-Stock / Tuned 23-Yr",
        "point_multiplier": 1.0,
        "model_key": "NVDA_23yr_multi_tf",
        "notes": "High daily ATR liquidity leader; ideal for structural Swing High/Low tests.",
    },
    {
        "symbol": "TSLL",
        "name": "Direxion Daily TSLA Bull 2X Shares",
        "category": "Leveraged ETF (Doug 3R Favorite)",
        "point_multiplier": 1.0,
        "model_key": "SPY_23yr_multi_tf",
        "notes": "Doug's benchmark small-account vehicle (~$0.70 Daily ATR, granular $20–$50 share sizing).",
    },
    {
        "symbol": "TQQQ",
        "name": "ProShares UltraPro QQQ (3x Nasdaq)",
        "category": "Leveraged ETF",
        "point_multiplier": 1.0,
        "model_key": "QQQ_23yr_multi_tf",
        "notes": "Cost-effective 3x leveraged Nasdaq vehicle for $50 risk unit accounts.",
    },
    {
        "symbol": "SOXL",
        "name": "Direxion Daily Semiconductor Bull 3X",
        "category": "Leveraged ETF",
        "point_multiplier": 1.0,
        "model_key": "NVDA_23yr_multi_tf",
        "notes": "High-beta semiconductor leveraged ETF for tight structural stop execution.",
    },
    {
        "symbol": "TLT",
        "name": "iShares 20+ Year Treasury Bond ETF",
        "category": "Macro / Tuned 23-Yr",
        "point_multiplier": 1.0,
        "model_key": "MACRO_TLT_GLD_23yr_multi_tf",
        "notes": "Macro rates vehicle with strict daily ATR boundaries.",
    },
    {
        "symbol": "GLD",
        "name": "SPDR Gold Shares (GC Proxy)",
        "category": "Macro / Tuned 23-Yr",
        "point_multiplier": 1.0,
        "model_key": "MACRO_TLT_GLD_23yr_multi_tf",
        "notes": "Gold macro proxy with clean multi-day Swing High / Swing Low pivots.",
    },
    {
        "symbol": "GME",
        "name": "GameStop Corp (High-Volatility Equity)",
        "category": "Single-Stock / Tuned 23-Yr",
        "point_multiplier": 1.0,
        "model_key": "GME_23yr_multi_tf",
        "notes": "Demonstrates ATR Exhaustion (>100% ATR) and Chased Breakout Trap filtering.",
    },
]


def _build_synthetic_scenario_frames(
    scenario: str,
    base_price: float = 580.0,
    daily_atr: float = 6.0,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Creates deterministic multi-day 1D and 5M OHLCV DataFrames for educational
    scenario testing (Topside Compression Short, Bullish Dip Long, Chased Breakout Trap, ATR Exhaustion).
    """
    rng = np.random.default_rng(42)
    dates_1d = pd.date_range("2026-07-01 04:00:00", periods=65, freq="B")

    scenario_key = (scenario or "").strip().lower()
    if scenario_key == "topside_short":
        # Bearish regime: price below 50 SMA; today rallies into Range High / Swing High consuming ~75% ATR then compresses
        closes_1d = np.linspace(base_price + 22.0, base_price - 8.0, 65)
        closes_1d[-2] = base_price - 6.0  # Previous day close = 574.0
        highs_1d = closes_1d + daily_atr * 0.55
        lows_1d = closes_1d - daily_atr * 0.45
        opens_1d = closes_1d + rng.uniform(-1.0, 1.0, size=65)
        # Set clear Swing High 8 days back and Previous Day Range High / Range Low
        highs_1d[-10] = base_price - 0.80  # Swing High = 579.20
        highs_1d[-2] = base_price - 2.20   # Range High (PDH) = 577.80
        lows_1d[-2] = base_price - 8.20    # Range Low (PDL) = 571.80
        lows_1d[-12] = base_price - 11.00  # Swing Low = 569.00

        # Today on 1D: rallies from 573.80 up to 578.30 (in Sell Zone between RH 577.80 and SH 579.20, 75% of $6 ATR)
        opens_1d[-1] = base_price - 6.20
        lows_1d[-1] = base_price - 6.30
        highs_1d[-1] = base_price - 1.70
        closes_1d[-1] = base_price - 2.05  # Current price 577.95 (inside Sell Zone, below 50 SMA ~585)
    elif scenario_key == "chased_breakout_trap":
        # Bearish regime (< 50 SMA), price surges straight into PDH/SH after consuming 92% of Daily ATR
        closes_1d = np.linspace(base_price + 24.0, base_price - 7.0, 65)
        highs_1d = closes_1d + daily_atr * 0.55
        lows_1d = closes_1d - daily_atr * 0.45
        opens_1d = closes_1d.copy()
        highs_1d[-9] = base_price - 0.50   # Swing High = 579.50
        highs_1d[-2] = base_price - 1.80   # Range High = 578.20
        lows_1d[-2] = base_price - 7.80    # Range Low = 572.20
        lows_1d[-14] = base_price - 10.50  # Swing Low = 569.50
        opens_1d[-1] = base_price - 7.20
        lows_1d[-1] = base_price - 7.40
        highs_1d[-1] = base_price - 1.70   # 5.70 expansion on ~6.0 ATR (95% ATR consumed!)
        closes_1d[-1] = base_price - 1.72
    else:
        # Default: Bullish Dip Reversal (Long Setup) — Price > 50 SMA, pulling back into Range Low / Swing Low
        closes_1d = np.linspace(base_price - 22.0, base_price + 8.0, 65)
        closes_1d[-2] = base_price + 6.0   # Prev close = 586.0
        highs_1d = closes_1d + daily_atr * 0.52
        lows_1d = closes_1d - daily_atr * 0.48
        opens_1d = closes_1d.copy()
        highs_1d[-8] = base_price + 11.20  # Swing High = 591.20
        highs_1d[-2] = base_price + 8.80   # Range High (PDH) = 588.80
        lows_1d[-2] = base_price + 3.20    # Range Low (PDL) = 583.20
        lows_1d[-10] = base_price + 1.40   # Swing Low = 581.40
        # Today pulls back from 585.80 into 583.10 (Buy Zone near RL 583.20 / SL 581.40, above 50 SMA ~574)
        opens_1d[-1] = base_price + 5.80
        highs_1d[-1] = base_price + 6.10
        lows_1d[-1] = base_price + 2.95
        closes_1d[-1] = base_price + 3.15

    daily_df = pd.DataFrame({
        "timestamps": dates_1d,
        "open": opens_1d,
        "high": highs_1d,
        "low": lows_1d,
        "close": closes_1d,
        "volume": np.full(65, 42_000_000.0),
        "amount": closes_1d * 42_000_000.0,
    })

    # Build 3 days of 5-minute candles (234 bars) matching the last 3 daily sessions
    bars_per_day = 78
    total_5m = bars_per_day * 3
    ts_list: List[pd.Timestamp] = []
    for d_idx in (-3, -2, -1):
        day_date = dates_1d[d_idx].strftime("%Y-%m-%d")
        day_times = pd.date_range(f"{day_date} 09:30:00", periods=bars_per_day, freq="5min")
        ts_list.extend(day_times)

    o_list, h_list, l_list, c_list = [], [], [], []
    for d_idx in (-3, -2, -1):
        d_open = float(daily_df["open"].iloc[d_idx])
        d_high = float(daily_df["high"].iloc[d_idx])
        d_low = float(daily_df["low"].iloc[d_idx])
        d_close = float(daily_df["close"].iloc[d_idx])

        # Smooth intraday path hitting d_low and d_high and ending at d_close with tight compression on last 6 bars
        t = np.linspace(0, 1, bars_per_day)
        if d_close >= d_open and scenario_key in ("topside_short", "chased_breakout_trap") and d_idx == -1:
            # Morning rally from low to high, compressing at the top
            curve = d_low + (d_high - d_low) * (1.0 - (1.0 - t) ** 2.2)
            curve[-6:] = np.linspace(d_high - 0.12, d_close, 6)
        elif d_close < d_open and d_idx == -1:
            # Pullback from high into Range Low buy zone, absorbing at support
            curve = d_high - (d_high - d_low) * (1.0 - (1.0 - t) ** 2.2)
            curve[-6:] = np.linspace(d_low + 0.10, d_close, 6)
        else:
            curve = np.linspace(d_open, d_close, bars_per_day) + np.sin(t * np.pi) * ((d_high - d_low) * 0.25)

        for b_i in range(bars_per_day):
            c_val = float(curve[b_i])
            o_val = float(curve[b_i - 1]) if b_i > 0 else d_open
            is_tail = (d_idx == -1 and b_i >= bars_per_day - 6)
            wick = 0.06 if is_tail else 0.22
            hi_val = max(o_val, c_val) + wick
            lo_val = min(o_val, c_val) - wick
            o_list.append(o_val)
            h_list.append(hi_val)
            l_list.append(lo_val)
            c_list.append(c_val)

        # Ensure exact session high/low match on previous day (-2) and current day (-1)
        day_start = (d_idx + 3) * bars_per_day
        h_list[day_start + 35] = max(h_list[day_start + 35], d_high)
        l_list[day_start + 12] = min(l_list[day_start + 12], d_low)
        c_list[day_start + bars_per_day - 1] = d_close

    intraday_5m_df = pd.DataFrame({
        "timestamps": ts_list,
        "open": o_list,
        "high": h_list,
        "low": l_list,
        "close": c_list,
        "volume": np.full(total_5m, 185_000.0),
        "amount": np.array(c_list) * 185_000.0,
    })

    return daily_df, intraday_5m_df


def load_multi_timeframe_data(
    ticker: str,
    data_source: str = "local",
    live_feed: Any = None,
    session_offset: int = 0,
    scenario_preset: str = "live_market",
) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    """
    Loads synchronized Daily (1D) and Intraday (5M) OHLCV DataFrames for a given ticker.
    Supports:
    - Guided 3R Scenario Presets (`topside_short`, `bullish_dip_long`, `chased_breakout_trap`)
    - Local 23-year multi-timeframe CSV datasets (`SPY`, `QQQ`, `IWM`, `NVDA`, `GME`, `TLT`, `GLD`, etc.)
    - Live Polygon API candle feed (`live_feed`)
    """
    clean_ticker = (ticker or "SPY").strip().upper()
    preset = (scenario_preset or "live_market").strip().lower()

    if preset in ("topside_short", "bullish_dip_long", "chased_breakout_trap"):
        # Seed base price from local CSV if available so prices reflect the selected ticker
        base_p = 580.0
        base_atr = 6.0
        csv_1d = resolve_local_dataset_csv(clean_ticker, "1day")
        if csv_1d and csv_1d.is_file():
            try:
                sample_1d = pd.read_csv(csv_1d).tail(20)
                base_p = float(sample_1d["close"].iloc[-1])
                base_atr = max(float((sample_1d["high"] - sample_1d["low"]).mean()), base_p * 0.01)
            except Exception:
                pass
        d_df, m_df = _build_synthetic_scenario_frames(preset, base_price=base_p, daily_atr=base_atr)
        return d_df, m_df, f"3R_SCENARIO_SIMULATION ({preset.upper()})"

    # Live Polygon feed mode
    if data_source == "live" and live_feed is not None:
        try:
            d_live, _ = live_feed.candles(clean_ticker, 1440, 120)
            m_live, _ = live_feed.candles(clean_ticker, 5, 512)
            return d_live, m_live, "POLYGON_LIVE_FEED"
        except Exception:
            # Graceful fallback to local research dataset if Polygon is offline/rate-limited
            pass

    csv_1d = resolve_local_dataset_csv(clean_ticker, "1day")
    csv_5m = resolve_local_dataset_csv(clean_ticker, "5min")

    # Fallback for leveraged ETFs (e.g. TSLL, TQQQ, SOXL) if no dedicated CSV exists: scale proxy CSV
    scale_factor = 1.0
    proxy_note = ""
    if not csv_1d or not csv_5m:
        proxy_map = {
            "TSLL": ("NVDA", 0.18),
            "TQQQ": ("QQQ", 0.14),
            "SOXL": ("NVDA", 0.32),
            "ES": ("SPY", 10.0),
            "MES": ("SPY", 10.0),
            "NQ": ("QQQ", 40.0),
            "MNQ": ("QQQ", 40.0),
        }
        proxy_ticker, scale_factor = proxy_map.get(clean_ticker, ("SPY", 1.0))
        csv_1d = resolve_local_dataset_csv(proxy_ticker, "1day")
        csv_5m = resolve_local_dataset_csv(proxy_ticker, "5min")
        if clean_ticker != proxy_ticker:
            proxy_note = f" (Scaled from {proxy_ticker})"

    if not csv_1d or not csv_1d.is_file() or not csv_5m or not csv_5m.is_file():
        d_df, m_df = _build_synthetic_scenario_frames("bullish_dip_long")
        return d_df, m_df, "SYNTHETIC_FALLBACK"

    daily_df = pd.read_csv(csv_1d, parse_dates=["timestamps"]).tail(250).reset_index(drop=True)
    # Read tail of 5M CSV efficiently
    intraday_5m_df = pd.read_csv(csv_5m, parse_dates=["timestamps"]).tail(3500).reset_index(drop=True)

    if scale_factor != 1.0:
        for col in ("open", "high", "low", "close"):
            daily_df[col] = (daily_df[col].astype(float) * scale_factor).round(4)
            intraday_5m_df[col] = (intraday_5m_df[col].astype(float) * scale_factor).round(4)

    # Apply optional historical session offset (days back)
    if session_offset > 0 and len(daily_df) > session_offset + 55:
        daily_df = daily_df.iloc[:-session_offset].reset_index(drop=True)
        cutoff_date = pd.to_datetime(daily_df["timestamps"]).iloc[-1].date()
        ts_5m = pd.to_datetime(intraday_5m_df["timestamps"])
        if getattr(ts_5m.dt, "tz", None) is not None:
            ts_5m = ts_5m.dt.tz_convert("UTC").dt.tz_localize(None)
        mask = ts_5m.dt.date <= cutoff_date
        if mask.sum() >= 60:
            intraday_5m_df = intraday_5m_df[mask].reset_index(drop=True)

    # Trim intraday_5m_df to regular trading hours (13:30 - 20:00 UTC / 09:30 - 16:00 ET) if available
    # so the chart displays clean session action rather than illiquid overnight ticks
    ts_5m_norm = pd.to_datetime(intraday_5m_df["timestamps"])
    if getattr(ts_5m_norm.dt, "tz", None) is not None:
        ts_5m_norm = ts_5m_norm.dt.tz_convert("UTC").dt.tz_localize(None)
    rth_mask = (ts_5m_norm.dt.hour >= 13) & (ts_5m_norm.dt.hour <= 20)
    if rth_mask.sum() >= 150:
        intraday_5m_df = intraday_5m_df[rth_mask].reset_index(drop=True)

    return daily_df, intraday_5m_df, f"LOCAL_23YR_RESEARCH_CSV{proxy_note}"


def build_3r_chart_bundle(
    ticker: str,
    daily_df: pd.DataFrame,
    intraday_5m_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    structure: MarketStructure,
    confluence: ConfluenceEvaluation,
) -> Dict[str, Any]:
    """
    Builds two synchronized Plotly dark-theme figures matching Section 2 & Section 4 of the specification:
    1. `daily_macro_chart`: View 1 — Daily Macro Timeframe (1D) with 50-Day SMA, Swing High/Low markers, and 14-Day ATR subpanel.
    2. `intraday_execution_chart`: View 2 — Intraday Execution Timeframe (5M) with:
       - 5-Minute Candlestick price series
       - Kronos autoregressive forecast candlesticks + volatility cone (`env_high` / `env_low`)
       - 4 Horizontal Liquidity Levels (`Swing High`, `Range High`, `Range Low`, `Swing Low`)
       - Shaded Institutional Sell Zone (RH to SH) & Buy Zone (SL to RL)
       - Daily 50-SMA reference line
       - Interactive Structural Stop-Loss & Take-Profit Target lines
    """
    analyzer = StructuralAnalyzer()
    d_clean = analyzer._prepare_df(daily_df).tail(90).reset_index(drop=True)
    d_clean["sma_50"] = analyzer.calculate_sma_series( analyzer._prepare_df(daily_df), 50).tail(len(d_clean)).values
    d_clean["atr_14"] = analyzer.calculate_atr_series(analyzer._prepare_df(daily_df), 14).tail(len(d_clean)).values

    # --- VIEW 1: DAILY MACRO TIMEFRAME (1D) ---
    fig_daily = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.07,
        row_heights=[0.72, 0.28],
        subplot_titles=(
            f"{ticker} · VIEW 1: DAILY MACRO TIMEFRAME (1D) & 50-DAY SMA ({structure.trend_regime} REGIME)",
            "DAILY 14-PERIOD AVERAGE TRUE RANGE (ATR BUDGET)",
        ),
    )

    d_x = d_clean["timestamps"].dt.strftime("%Y-%m-%d")
    fig_daily.add_trace(
        go.Candlestick(
            x=d_x,
            open=d_clean["open"],
            high=d_clean["high"],
            low=d_clean["low"],
            close=d_clean["close"],
            name="1D Candles",
            increasing_line_color="#10b981",
            decreasing_line_color="#ef4444",
        ),
        row=1,
        col=1,
    )
    fig_daily.add_trace(
        go.Scatter(
            x=d_x,
            y=d_clean["sma_50"],
            mode="lines",
            name="50-Day SMA (Trend Gate)",
            line=dict(color="#38bdf8", width=2.6),
        ),
        row=1,
        col=1,
    )
    # Overlay Swing High & Swing Low reference lines on 1D chart
    fig_daily.add_hline(
        y=structure.swing_high,
        line_dash="dash",
        line_color="#f87171",
        line_width=1.3,
        annotation_text=f"Swing High ${structure.swing_high:.2f}",
        annotation_position="top left",
        annotation_font=dict(color="#fca5a5", size=10),
        row=1,
        col=1,
    )
    fig_daily.add_hline(
        y=structure.swing_low,
        line_dash="dash",
        line_color="#34d399",
        line_width=1.3,
        annotation_text=f"Swing Low ${structure.swing_low:.2f}",
        annotation_position="bottom left",
        annotation_font=dict(color="#6ee7b7", size=10),
        row=1,
        col=1,
    )

    fig_daily.add_trace(
        go.Scatter(
            x=d_x,
            y=d_clean["atr_14"],
            mode="lines",
            fill="tozeroy",
            name="14-Day ATR ($)",
            line=dict(color="#f59e0b", width=2.0),
            fillcolor="rgba(245, 158, 11, 0.16)",
        ),
        row=2,
        col=1,
    )

    fig_daily.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0b1120",
        plot_bgcolor="#0f172a",
        height=460,
        margin=dict(l=52, r=28, t=54, b=36),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0, font=dict(size=11)),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
    )
    fig_daily.update_xaxes(type="category", nticks=10, gridcolor="rgba(148, 163, 184, 0.12)")
    fig_daily.update_yaxes(gridcolor="rgba(148, 163, 184, 0.12)")

    # --- VIEW 2: INTRADAY EXECUTION TIMEFRAME (5M) + KRONOS FORECAST + 4 LIQUIDITY LEVELS ---
    m_clean = analyzer._prepare_df(intraday_5m_df).tail(96).reset_index(drop=True)
    hist_x = [ts.strftime("%m-%d %H:%M") for ts in pd.to_datetime(m_clean["timestamps"])]

    pred_ts = pd.to_datetime(pred_df.index) if not isinstance(pred_df.index, pd.RangeIndex) else pd.date_range(
        pd.to_datetime(m_clean["timestamps"].iloc[-1]) + pd.Timedelta(minutes=5),
        periods=len(pred_df),
        freq="5min",
    )
    pred_x = [ts.strftime("%m-%d %H:%M") for ts in pred_ts]
    all_x = hist_x + pred_x

    fig_5m = go.Figure()

    # Shaded Upper Institutional Sell Zone (Range High to Swing High)
    if structure.swing_high > structure.range_high:
        fig_5m.add_hrect(
            y0=structure.range_high,
            y1=structure.swing_high,
            fillcolor="rgba(239, 68, 68, 0.11)",
            line_width=0,
            annotation_text="INSTITUTIONAL SELL ZONE (RH → SH)",
            annotation_position="top left",
            annotation_font=dict(color="#fca5a5", size=10),
        )
    # Shaded Lower Institutional Buy Zone (Swing Low to Range Low)
    if structure.range_low > structure.swing_low:
        fig_5m.add_hrect(
            y0=structure.swing_low,
            y1=structure.range_low,
            fillcolor="rgba(16, 185, 129, 0.11)",
            line_width=0,
            annotation_text="INSTITUTIONAL BUY ZONE (SL → RL)",
            annotation_position="bottom left",
            annotation_font=dict(color="#6ee7b7", size=10),
        )

    # Historical 5M Candlesticks
    fig_5m.add_trace(
        go.Candlestick(
            x=hist_x,
            open=m_clean["open"],
            high=m_clean["high"],
            low=m_clean["low"],
            close=m_clean["close"],
            name=f"5M Price ({len(m_clean)} bars)",
            increasing_line_color="#10b981",
            decreasing_line_color="#ef4444",
        )
    )

    # Kronos Volatility Cone (`env_high` / `env_low`)
    if "env_high" in pred_df.columns and "env_low" in pred_df.columns:
        cone_x = [hist_x[-1]] + pred_x
        cone_upper = [float(m_clean["close"].iloc[-1])] + [float(v) for v in pred_df["env_high"].values]
        cone_lower = [float(m_clean["close"].iloc[-1])] + [float(v) for v in pred_df["env_low"].values]
        fig_5m.add_trace(
            go.Scatter(
                x=cone_x + cone_x[::-1],
                y=cone_upper + cone_lower[::-1],
                fill="toself",
                fillcolor="rgba(168, 85, 247, 0.16)",
                line=dict(color="rgba(168, 85, 247, 0.35)", width=1),
                name="Kronos Forecast Cone",
                hoverinfo="skip",
            )
        )

    # Kronos Autoregressive Forecast Candlesticks
    fig_5m.add_trace(
        go.Candlestick(
            x=pred_x,
            open=pred_df["open"],
            high=pred_df["high"],
            low=pred_df["low"],
            close=pred_df["close"],
            name=f"Kronos Forecast ({len(pred_df)} bars)",
            increasing_line_color="#a855f7",
            decreasing_line_color="#ec4899",
        )
    )

    # Kronos Median / Medoid Trajectory Line
    fig_5m.add_trace(
        go.Scatter(
            x=[hist_x[-1]] + pred_x,
            y=[float(m_clean["close"].iloc[-1])] + [float(v) for v in pred_df["close"].values],
            mode="lines+markers",
            name="Kronos Projected Path",
            line=dict(color="#c084fc", width=2.2, dash="dot"),
            marker=dict(size=4),
        )
    )

    # Daily 50-SMA Trajectory Line overlaid on 5M
    fig_5m.add_trace(
        go.Scatter(
            x=[all_x[0], all_x[-1]],
            y=[structure.sma_50, structure.sma_50],
            mode="lines",
            name=f"Daily 50-SMA (${structure.sma_50:.2f})",
            line=dict(color="#38bdf8", width=2.0, dash="dashdot"),
        )
    )

    # 4 Horizontal Liquidity Levels per Section 4 Panel 2 Specification:
    # 1. Swing High (Red, dashed line)
    fig_5m.add_hline(
        y=structure.swing_high,
        line_dash="dash",
        line_color="#ef4444",
        line_width=1.8,
        annotation_text=f"SWING HIGH (SH): ${structure.swing_high:.2f}",
        annotation_position="top right",
        annotation_font=dict(color="#fca5a5", size=11),
    )
    # 2. Range High / PDH (Red, solid line)
    fig_5m.add_hline(
        y=structure.range_high,
        line_dash="solid",
        line_color="#f87171",
        line_width=2.2,
        annotation_text=f"RANGE HIGH (PDH): ${structure.range_high:.2f}",
        annotation_position="bottom right",
        annotation_font=dict(color="#fecaca", size=11),
    )
    # 3. Range Low / PDL (Green, solid line)
    fig_5m.add_hline(
        y=structure.range_low,
        line_dash="solid",
        line_color="#10b981",
        line_width=2.2,
        annotation_text=f"RANGE LOW (PDL): ${structure.range_low:.2f}",
        annotation_position="top right",
        annotation_font=dict(color="#a7f3d0", size=11),
    )
    # 4. Swing Low (Green, dashed line)
    fig_5m.add_hline(
        y=structure.swing_low,
        line_dash="dash",
        line_color="#059669",
        line_width=1.8,
        annotation_text=f"SWING LOW (SL): ${structure.swing_low:.2f}",
        annotation_position="bottom right",
        annotation_font=dict(color="#6ee7b7", size=11),
    )

    # Structural Stop-Loss & Structural Target Lines
    fig_5m.add_hline(
        y=confluence.structural_stop,
        line_dash="dot",
        line_color="#fbbf24",
        line_width=2.2,
        annotation_text=f"STRUCTURAL STOP: ${confluence.structural_stop:.2f}",
        annotation_position="top left",
        annotation_font=dict(color="#fde68a", size=11),
    )
    fig_5m.add_hline(
        y=confluence.structural_target,
        line_dash="dot",
        line_color="#22d3ee",
        line_width=2.0,
        annotation_text=f"3R TARGET: ${confluence.structural_target:.2f} ({confluence.estimated_rr:.2f}:1 R:R)",
        annotation_position="bottom left",
        annotation_font=dict(color="#a5f3fc", size=11),
    )

    fig_5m.update_layout(
        title=dict(
            text=(
                f"{ticker} · VIEW 2: INTRADAY EXECUTION (5M) + KRONOS FORECAST + 4 LIQUIDITY LEVELS "
                f"[{confluence.setup_archetype}]"
            ),
            font=dict(size=13, color="#f8fafc"),
        ),
        template="plotly_dark",
        paper_bgcolor="#0b1120",
        plot_bgcolor="#0f172a",
        height=540,
        margin=dict(l=52, r=32, t=58, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0, font=dict(size=11)),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
    )
    fig_5m.update_xaxes(type="category", nticks=12, gridcolor="rgba(148, 163, 184, 0.12)")
    fig_5m.update_yaxes(gridcolor="rgba(148, 163, 184, 0.12)")

    return {
        "daily_macro_chart": json.loads(json.dumps(fig_daily, cls=PlotlyJSONEncoder)),
        "intraday_execution_chart": json.loads(json.dumps(fig_5m, cls=PlotlyJSONEncoder)),
    }


def _heuristic_kronos_fallback_forecast(
    intraday_5m_df: pd.DataFrame,
    structure: MarketStructure,
    pred_len: int = 24,
    scenario_preset: str = "live_market",
) -> pd.DataFrame:
    """
    Fast deterministic fallback forecast trajectory used only if PyTorch model weights
    are not loaded or when running unit tests without GPU weights.
    """
    last_row = intraday_5m_df.iloc[-1]
    last_close = float(last_row["close"])
    last_ts = pd.to_datetime(last_row["timestamps"]) if "timestamps" in intraday_5m_df.columns else pd.Timestamp("2026-10-09 15:30:00")
    future_index = pd.date_range(last_ts + pd.Timedelta(minutes=5), periods=pred_len, freq="5min")

    preset = (scenario_preset or "").strip().lower()
    if preset == "chased_breakout_trap":
        # Contrarian bullish extension exceeding remaining ATR to trigger trap & unfeasible reward check
        target_move = max(structure.remaining_atr * 1.4, 0.35 * structure.atr_14)
    elif structure.trend_regime == "BEARISH":
        # Project downward mean reversion within remaining ATR budget
        target_move = -min(max(0.45 * structure.remaining_atr, 0.18 * structure.atr_14), max(structure.remaining_atr * 0.9, 0.25))
    else:
        # Project upward bounce within remaining ATR budget
        target_move = min(max(0.55 * structure.remaining_atr, 0.22 * structure.atr_14), max(structure.remaining_atr * 0.9, 0.25))

    steps = np.linspace(0, 1, pred_len)
    closes = last_close + target_move * (steps ** 0.85)
    opens = np.concatenate([[last_close], closes[:-1]])
    bar_span = max(0.03 * structure.atr_14, last_close * 0.0008)
    highs = np.maximum(opens, closes) + bar_span * 0.6
    lows = np.minimum(opens, closes) - bar_span * 0.6

    pred_df = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.full(pred_len, float(last_row.get("volume", 100000.0))),
            "amount": closes * float(last_row.get("volume", 100000.0)),
            "env_high": highs + bar_span * 1.1,
            "env_low": lows - bar_span * 1.1,
        },
        index=future_index,
    )
    return pred_df


def run_3r_system_evaluation(
    ticker: str = "SPY",
    predictor: Any = None,
    data_source: str = "local",
    live_feed: Any = None,
    pred_len: int = 24,
    lookback: int = 256,
    temperature: float = 0.25,
    top_p: float = 0.9,
    sample_count: int = 5,
    account_balance: float = 5000.0,
    base_balance: float = 5000.0,
    max_risk_dollars: float = 50.0,
    profitable_days_this_week: int = 3,
    consecutive_consistent_weeks: int = 2,
    session_offset: int = 0,
    scenario_preset: str = "live_market",
) -> Dict[str, Any]:
    """
    End-to-end 3R Rule Trading System pipeline:
    1. Loads Daily (1D) and Intraday (5M) OHLCV data.
    2. Computes `MarketStructure` (50-SMA regime, 4 Liquidity Levels, 14-ATR budget).
    3. Runs Kronos candlestick forecast (`generate_and_evaluate_forecast`) & evaluates 0–100 Confluence Score.
    4. Computes Structural Stop-Loss & Position Sizing (`calculate_trade_sizing`).
    5. Computes "Wall Street Raise" 10% Scaling Tracker (`evaluate_scaling_eligibility`).
    6. Builds synchronized 1D and 5M Plotly chart JSON bundles.
    """
    t0 = time.perf_counter()
    clean_ticker = (ticker or "SPY").strip().upper()
    daily_df, intraday_5m_df, provenance = load_multi_timeframe_data(
        ticker=clean_ticker,
        data_source=data_source,
        live_feed=live_feed,
        session_offset=session_offset,
        scenario_preset=scenario_preset,
    )

    analyzer = StructuralAnalyzer()
    structure = analyzer.analyze(daily_df=daily_df, intraday_5m_df=intraday_5m_df)

    spec = TICKER_TO_MODEL_MAP.get(clean_ticker, TICKER_TO_MODEL_MAP["SPY"])
    norm_mode = spec.get("normalization_mode", "detrend")

    preset_key = (scenario_preset or "live_market").strip().lower()
    use_real_model = bool(predictor is not None and preset_key == "live_market")

    if use_real_model:
        pred_df, confluence_score, confluence_eval = generate_and_evaluate_forecast(
            predictor=predictor,
            intraday_5m_df=intraday_5m_df,
            structure=structure,
            pred_len=pred_len,
            lookback=lookback,
            temperature=temperature,
            top_p=top_p,
            sample_count=sample_count,
            normalization_mode=norm_mode,
            selection_mode="medoid",
        )
        inference_engine = f"Kronos Neural Foundation Model ({spec.get('model_key', 'SPY_23yr_multi_tf')})"
    else:
        pred_df = _heuristic_kronos_fallback_forecast(
            intraday_5m_df=intraday_5m_df,
            structure=structure,
            pred_len=pred_len,
            scenario_preset=preset_key,
        )
        confluence_eval = evaluate_forecast_confluence(
            pred_df=pred_df,
            intraday_5m_df=intraday_5m_df,
            structure=structure,
        )
        confluence_score = confluence_eval.confluence_score
        inference_engine = (
            f"3R Guided Scenario Engine ({preset_key})"
            if preset_key != "live_market"
            else "Kronos Structural Trajectory Engine"
        )

    sizing = calculate_trade_sizing(
        account_balance=account_balance,
        max_risk_dollars=max_risk_dollars,
        entry_price=confluence_eval.structural_entry,
        structural_stop_price=confluence_eval.structural_stop,
        target_price=confluence_eval.structural_target,
    )

    scaling = evaluate_scaling_eligibility(
        base_balance=base_balance,
        current_balance=account_balance,
        profitable_days_this_week=profitable_days_this_week,
        consecutive_consistent_weeks=consecutive_consistent_weeks,
        base_shares=50,
        base_risk_dollars=max_risk_dollars,
    )

    charts = build_3r_chart_bundle(
        ticker=clean_ticker,
        daily_df=daily_df,
        intraday_5m_df=intraday_5m_df,
        pred_df=pred_df,
        structure=structure,
        confluence=confluence_eval,
    )

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)

    forecast_bars = []
    for ts, row in pred_df.iterrows():
        forecast_bars.append({
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "open": round(float(row["open"]), 4),
            "high": round(float(row["high"]), 4),
            "low": round(float(row["low"]), 4),
            "close": round(float(row["close"]), 4),
        })

    return {
        "success": True,
        "ticker": clean_ticker,
        "provenance": provenance,
        "inference_engine": inference_engine,
        "latency_ms": elapsed_ms,
        "structure": structure.to_dict(),
        "confluence": confluence_eval.to_dict(),
        "confluence_score": confluence_score,
        "sizing": sizing,
        "scaling": scaling,
        "charts": charts,
        "forecast_bars": forecast_bars,
        "recommended_assets": RECOMMENDED_3R_ASSETS,
    }


def register_3r_trading_system(app, ui_module, live_feed=None) -> Blueprint:
    """
    Registers the dedicated `/3r-trading-system` page and `/api/3r/*` analytical endpoints
    on the Kronos Flask application.
    """
    three_r_bp = Blueprint("three_r_trading_system", __name__)
    predictor_cache: Dict[str, Any] = {}
    lock = threading.Lock()

    def _get_device() -> str:
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def _get_predictor_for_ticker(ticker: str, requested_model_key: Optional[str] = None):
        if not getattr(ui_module, "MODEL_AVAILABLE", False):
            return None
        spec = TICKER_TO_MODEL_MAP.get(ticker.upper(), TICKER_TO_MODEL_MAP["SPY"])
        model_key = requested_model_key or spec["model_key"]
        if model_key not in ui_module.AVAILABLE_MODELS:
            model_key = "SPY_23yr_multi_tf" if "SPY_23yr_multi_tf" in ui_module.AVAILABLE_MODELS else next(iter(ui_module.AVAILABLE_MODELS.keys()), None)
        if not model_key:
            return None

        with lock:
            if model_key in predictor_cache:
                return predictor_cache[model_key]
            try:
                from model import Kronos, KronosTokenizer
                from model.enhanced_predictor import EnhancedKronosPredictor

                cfg = ui_module.AVAILABLE_MODELS[model_key]
                device = _get_device()
                tok = KronosTokenizer.from_pretrained(cfg["tokenizer_id"])
                mdl = Kronos.from_pretrained(cfg["model_id"])
                tok.eval()
                mdl.eval()
                pred = EnhancedKronosPredictor(mdl, tok, device=device, max_context=cfg.get("context_length", 512))
                if len(predictor_cache) >= 2:
                    predictor_cache.clear()
                predictor_cache[model_key] = pred
                return pred
            except Exception as exc:
                print(f"[3R System] Warning loading model {model_key}: {exc}")
                return getattr(ui_module, "predictor", None)

    @three_r_bp.get("/3r-trading-system")
    @three_r_bp.get("/3r")
    def render_3r_page():
        """Renders the standalone 3R Rule Trading System page."""
        return render_template(
            "3r_trading_system.html",
            recommended_assets=RECOMMENDED_3R_ASSETS,
            tuned_models=TUNED_MODEL_CATALOG,
        )

    @three_r_bp.post("/api/3r/analyze")
    def api_3r_analyze():
        """Runs full 3R multi-timeframe structural analysis + Kronos forecast + confluence + sizing."""
        body = request.get_json(silent=True) or {}
        ticker = str(body.get("ticker", "SPY")).strip().upper()
        model_key = body.get("model_key") or None
        data_source = str(body.get("data_source", "local")).strip().lower()
        pred_len = max(6, min(78, int(body.get("pred_len", 24))))
        lookback = max(64, min(512, int(body.get("lookback", 256))))
        temperature = max(0.05, min(1.2, float(body.get("temperature", 0.25))))
        top_p = max(0.1, min(1.0, float(body.get("top_p", 0.9))))
        sample_count = max(1, min(10, int(body.get("sample_count", 3))))
        account_balance = max(100.0, float(body.get("account_balance", 5000.0)))
        base_balance = max(100.0, float(body.get("base_balance", 5000.0)))
        max_risk_dollars = max(5.0, float(body.get("max_risk_dollars", 50.0)))
        profitable_days = max(0, min(5, int(body.get("profitable_days_this_week", 3))))
        consecutive_weeks = max(0, int(body.get("consecutive_consistent_weeks", 2)))
        session_offset = max(0, min(120, int(body.get("session_offset", 0))))
        scenario_preset = str(body.get("scenario_preset", "live_market")).strip().lower()
        use_kronos_model = bool(body.get("use_kronos_model", True))

        predictor = _get_predictor_for_ticker(ticker, model_key) if (use_kronos_model and scenario_preset == "live_market") else None
        active_live_feed = app.config.get("THREE_R_LIVE_FEED") or live_feed

        try:
            result = run_3r_system_evaluation(
                ticker=ticker,
                predictor=predictor,
                data_source=data_source,
                live_feed=active_live_feed,
                pred_len=pred_len,
                lookback=lookback,
                temperature=temperature,
                top_p=top_p,
                sample_count=sample_count,
                account_balance=account_balance,
                base_balance=base_balance,
                max_risk_dollars=max_risk_dollars,
                profitable_days_this_week=profitable_days,
                consecutive_consistent_weeks=consecutive_weeks,
                session_offset=session_offset,
                scenario_preset=scenario_preset,
            )
            return jsonify(result)
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

    @three_r_bp.post("/api/3r/calculate-sizing")
    def api_3r_calculate_sizing():
        """Instant interactive endpoint for Panel 4 (Execution Sizing Calculator) & Panel 5 (Wall Street Raise)."""
        body = request.get_json(silent=True) or {}
        try:
            account_balance = float(body.get("account_balance", 5000.0))
            base_balance = float(body.get("base_balance", 5000.0))
            max_risk_dollars = float(body.get("max_risk_dollars", 50.0))
            entry_price = float(body.get("entry_price", 580.0))
            structural_stop_price = float(body.get("structural_stop_price", 579.0))
            target_price = float(body.get("target_price", 583.5))
            point_multiplier = float(body.get("point_multiplier", 1.0))
            profitable_days = int(body.get("profitable_days_this_week", 3))
            consecutive_weeks = int(body.get("consecutive_consistent_weeks", 2))

            sizing = calculate_trade_sizing(
                account_balance=account_balance,
                max_risk_dollars=max_risk_dollars,
                entry_price=entry_price,
                structural_stop_price=structural_stop_price,
                target_price=target_price,
                point_multiplier=point_multiplier,
            )
            scaling = evaluate_scaling_eligibility(
                base_balance=base_balance,
                current_balance=account_balance,
                profitable_days_this_week=profitable_days,
                consecutive_consistent_weeks=consecutive_weeks,
                base_shares=50,
                base_risk_dollars=max_risk_dollars,
            )
            return jsonify({"success": True, "sizing": sizing, "scaling": scaling})
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

    if "three_r_trading_system" not in app.blueprints:
        app.register_blueprint(three_r_bp)
    app.config["THREE_R_LIVE_FEED"] = live_feed
    return three_r_bp
