"""
Polygon.io Options Chain, Greeks, IV Surface, Max Pain, and Underlying Intelligence Engine.
Uses server-side credentials from .env; never exposes API keys to the browser.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlsplit
import math
import os
import re
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from plotly.utils import PlotlyJSONEncoder
import json
import requests
from dotenv import dotenv_values

from webui.polygon_feed import FeedError, settings

ROOT = Path(__file__).resolve().parents[1]

VALID_UNDERLYING_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")


def validate_equity_ticker(ticker: str) -> str:
    t = str(ticker or "SPY").strip().upper()
    if t.startswith("I:"):
        t = t[2:]
    if not VALID_UNDERLYING_RE.fullmatch(t):
        raise FeedError("Enter a valid US equity or ETF ticker (e.g. SPY, QQQ, IWM, NVDA, GME, TLT, GLD).")
    return t


def _polygon_get(path_or_url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    key, base = settings()
    if not key:
        raise FeedError("Polygon API key is missing from .env.", 503)
    if path_or_url.startswith("http"):
        parsed = urlsplit(path_or_url)
        if parsed.scheme != "https" or parsed.netloc != urlsplit(base).netloc:
            raise FeedError("Invalid provider URL.", 502)
        url = base + parsed.path
        merged_params = {k: v for k, v in parse_qsl(parsed.query) if k.lower() != "apikey"}
        if params:
            merged_params.update(params)
    else:
        url = f"{base}{path_or_url}"
        merged_params = dict(params or {})

    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {key}"},
            params=merged_params,
            timeout=(5, 25),
            allow_redirects=False,
        )
    except requests.RequestException:
        raise FeedError("Polygon connection failed or timed out.", 502) from None

    if resp.status_code in (401, 403):
        raise FeedError(f"Polygon access denied (HTTP {resp.status_code}). Check your plan entitlements.", resp.status_code)
    if resp.status_code == 429:
        raise FeedError("Polygon rate limit reached. Wait briefly and retry.", 429)
    if resp.status_code == 404:
        return {}
    if resp.status_code != 200:
        raise FeedError(f"Polygon returned HTTP {resp.status_code}.", 502)
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        raise FeedError("Polygon returned malformed JSON.", 502) from None


def fetch_underlying_intelligence(ticker: str) -> Dict[str, Any]:
    """
    Pulls comprehensive underlying snapshot, reference details, technical indicators (RSI, SMA, EMA, MACD),
    and latest news articles from Polygon.
    """
    ticker = validate_equity_ticker(ticker)
    snap_payload = _polygon_get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}")
    t_snap = snap_payload.get("ticker") or {}
    day = t_snap.get("day") or {}
    prev_day = t_snap.get("prevDay") or {}
    last_trade = t_snap.get("lastTrade") or {}
    last_quote = t_snap.get("lastQuote") or {}

    price = (
        last_trade.get("p")
        or day.get("c")
        or prev_day.get("c")
    )
    bid = last_quote.get("p")
    ask = last_quote.get("P")
    spread = round(float(ask) - float(bid), 4) if (bid is not None and ask is not None and ask >= bid > 0) else None

    # Reference details
    ref_payload = _polygon_get(f"/v3/reference/tickers/{ticker}")
    ref = ref_payload.get("results") or {}

    # Technical indicators (Daily 14/20 window)
    def _latest_ind(ind_name: str, extra_params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            p = {"timespan": "day", "adjusted": "true", "limit": 1, **extra_params}
            res = _polygon_get(f"/v1/indicators/{ind_name}/{ticker}", p)
            vals = (res.get("results") or {}).get("values") or []
            return vals[0] if vals else {}
        except FeedError:
            return {}

    rsi_obj = _latest_ind("rsi", {"window": 14, "series_type": "close"})
    sma_obj = _latest_ind("sma", {"window": 20, "series_type": "close"})
    ema_obj = _latest_ind("ema", {"window": 20, "series_type": "close"})
    macd_obj = _latest_ind("macd", {"short_window": 12, "long_window": 26, "signal_window": 9, "series_type": "close"})

    # Latest news
    news_items = []
    try:
        news_payload = _polygon_get("/v2/reference/news", {"ticker": ticker, "limit": 6})
        for item in (news_payload.get("results") or [])[:6]:
            news_items.append({
                "title": item.get("title", ""),
                "publisher": (item.get("publisher") or {}).get("name", "Polygon News"),
                "published_utc": item.get("published_utc", ""),
                "article_url": item.get("article_url", ""),
                "description": item.get("description", ""),
            })
    except FeedError:
        pass

    return {
        "ticker": ticker,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "price": float(price) if price is not None else None,
        "today_change": float(t_snap.get("todaysChange")) if t_snap.get("todaysChange") is not None else None,
        "today_change_pct": float(t_snap.get("todaysChangePerc")) if t_snap.get("todaysChangePerc") is not None else None,
        "day_open": float(day.get("o")) if day.get("o") is not None else None,
        "day_high": float(day.get("h")) if day.get("h") is not None else None,
        "day_low": float(day.get("l")) if day.get("l") is not None else None,
        "day_close": float(day.get("c")) if day.get("c") is not None else None,
        "day_volume": float(day.get("v")) if day.get("v") is not None else None,
        "day_vwap": float(day.get("vw")) if day.get("vw") is not None else None,
        "prev_close": float(prev_day.get("c")) if prev_day.get("c") is not None else None,
        "prev_volume": float(prev_day.get("v")) if prev_day.get("v") is not None else None,
        "bid": float(bid) if bid is not None else None,
        "ask": float(ask) if ask is not None else None,
        "spread": spread,
        "market_cap": float(ref.get("market_cap")) if ref.get("market_cap") is not None else None,
        "company_name": ref.get("name", ticker),
        "primary_exchange": ref.get("primary_exchange", ""),
        "sic_description": ref.get("sic_description", ""),
        "description": ref.get("description", ""),
        "homepage_url": ref.get("homepage_url", ""),
        "total_employees": ref.get("total_employees"),
        "rsi_14": float(rsi_obj.get("value")) if rsi_obj.get("value") is not None else None,
        "sma_20": float(sma_obj.get("value")) if sma_obj.get("value") is not None else None,
        "ema_20": float(ema_obj.get("value")) if ema_obj.get("value") is not None else None,
        "macd_val": float(macd_obj.get("value")) if macd_obj.get("value") is not None else None,
        "macd_signal": float(macd_obj.get("signal")) if macd_obj.get("signal") is not None else None,
        "macd_hist": float(macd_obj.get("histogram")) if macd_obj.get("histogram") is not None else None,
        "news": news_items,
        "raw": {"snapshot": t_snap, "reference": {k: ref.get(k) for k in ("name", "market_cap", "primary_exchange", "sic_description", "type")}},
    }


def _calculate_max_pain(df: pd.DataFrame) -> Optional[float]:
    """Calculates the option Max Pain strike where total intrinsic value paid to option holders is minimized."""
    if df.empty or "strike_price" not in df.columns:
        return None
    strikes = np.sort(df["strike_price"].unique())
    if len(strikes) == 0:
        return None
    calls = df[df["contract_type"] == "call"]
    puts = df[df["contract_type"] == "put"]
    call_strikes = calls["strike_price"].to_numpy(dtype=float)
    call_oi = calls["open_interest"].fillna(0).to_numpy(dtype=float)
    put_strikes = puts["strike_price"].to_numpy(dtype=float)
    put_oi = puts["open_interest"].fillna(0).to_numpy(dtype=float)

    best_strike = None
    min_payout = float("inf")
    for s in strikes:
        c_val = np.sum(np.maximum(0.0, s - call_strikes) * call_oi)
        p_val = np.sum(np.maximum(0.0, put_strikes - s) * put_oi)
        total = c_val + p_val
        if total < min_payout:
            min_payout = total
            best_strike = float(s)
    return best_strike


def build_options_charts(df: pd.DataFrame, ticker: str, spot_price: float, summary: Dict[str, Any]) -> Dict[str, str]:
    """Creates interactive TradingView-style Plotly charts for Open Interest / Gamma Exposure by Strike and IV Smile in Darkwave theme."""
    darkwave_layout = dict(
        template="plotly_dark",
        paper_bgcolor="#0c0e1a",
        plot_bgcolor="#080a12",
        font=dict(color="#e2e8f0", family="Inter, system-ui, sans-serif"),
        dragmode="pan",
        hovermode="x unified",
    )
    if df.empty:
        empty_fig = go.Figure()
        empty_fig.update_layout(title=f"{ticker}: No options contracts in selected filter", height=420, **darkwave_layout)
        enc = json.dumps(empty_fig, cls=PlotlyJSONEncoder)
        return {"oi_gex_chart": enc, "iv_smile_chart": enc}

    df_clean = df.copy()
    df_clean["weight"] = df_clean["open_interest"].fillna(0) + df_clean["volume"].fillna(0) * 2 + 1

    # Aggregate OI, Volume, and GEX by strike & contract_type
    grouped = df_clean.groupby(["strike_price", "contract_type"], as_index=False).agg(
        open_interest=("open_interest", "sum"),
        volume=("volume", "sum"),
        gex=("gex_dollars", "sum"),
    )
    calls = grouped[grouped["contract_type"] == "call"].sort_values("strike_price")
    puts = grouped[grouped["contract_type"] == "put"].sort_values("strike_price")

    # Compute typical strike spacing near spot so bar widths are always thick and readable
    all_strikes = np.sort(df_clean["strike_price"].unique())
    near_strikes = all_strikes[(all_strikes >= spot_price * 0.96) & (all_strikes <= spot_price * 1.04)]
    if len(near_strikes) >= 3:
        diffs = np.diff(near_strikes)
        pos_diffs = diffs[diffs > 0]
        strike_step = float(np.median(pos_diffs)) if len(pos_diffs) else 1.0
    else:
        strike_step = max(0.5, round(spot_price * 0.005, 2))
    bar_width_grouped = max(0.35, strike_step * 0.42)
    bar_width_single = max(0.45, strike_step * 0.72)

    # Default focused viewport around Spot (+/- 6.5%) while keeping all strikes available when panning/zooming out
    min_strike = float(all_strikes.min()) if len(all_strikes) else spot_price * 0.9
    max_strike = float(all_strikes.max()) if len(all_strikes) else spot_price * 1.1
    focus_low = max(min_strike, round(spot_price * 0.935, 2))
    focus_high = min(max_strike, round(spot_price * 1.065, 2))
    if focus_high <= focus_low:
        focus_low, focus_high = min_strike, max_strike

    max_pain = summary.get("max_pain_strike")
    call_wall = summary.get("call_wall_strike")
    put_wall = summary.get("put_wall_strike")

    # 1. Open Interest & Net GEX by Strike
    mp_str = f"${max_pain:.0f}" if max_pain else "N/A"
    cw_str = f"${call_wall:.0f}" if call_wall else "N/A"
    pw_str = f"${put_wall:.0f}" if put_wall else "N/A"
    fig1 = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.13,
        row_heights=[0.54, 0.46],
        subplot_titles=(
            f"{ticker} Open Interest by Strike  •  Spot: ${spot_price:.2f}  |  Max Pain: {mp_str}  |  Call Wall: {cw_str}  |  Put Wall: {pw_str}",
            f"{ticker} Dealer Net Gamma Exposure (GEX $M per 1% Move)  •  Cyan = Call Gamma Pin  |  Magenta = Put Gamma Accelerator"
        )
    )
    fig1.add_trace(
        go.Bar(
            x=calls["strike_price"],
            y=calls["open_interest"],
            name="Call OI",
            width=bar_width_grouped,
            marker_color="rgba(0, 245, 212, 0.88)",
            marker_line=dict(color="#00f5d4", width=0.8),
            hovertemplate="Strike $%{x:.2f}<br>Call OI: %{y:,}<extra></extra>",
        ),
        row=1, col=1
    )
    fig1.add_trace(
        go.Bar(
            x=puts["strike_price"],
            y=puts["open_interest"],
            name="Put OI",
            width=bar_width_grouped,
            marker_color="rgba(255, 42, 133, 0.88)",
            marker_line=dict(color="#ff2a85", width=0.8),
            hovertemplate="Strike $%{x:.2f}<br>Put OI: %{y:,}<extra></extra>",
        ),
        row=1, col=1
    )

    gex_by_strike = df_clean.groupby("strike_price", as_index=False)["gex_dollars"].sum().sort_values("strike_price")
    gex_m = gex_by_strike["gex_dollars"] / 1e6
    pos_gex = gex_m.clip(lower=0.0)
    neg_gex = gex_m.clip(upper=0.0)

    fig1.add_trace(
        go.Bar(
            x=gex_by_strike["strike_price"],
            y=pos_gex,
            name="+GEX (Call Dealer Long Gamma $M)",
            width=bar_width_single,
            marker_color="rgba(0, 245, 212, 0.90)",
            marker_line=dict(color="#00f5d4", width=1.0),
            hovertemplate="Strike $%{x:.2f}<br>Net +GEX: +$%{y:.2f}M<extra></extra>",
        ),
        row=2, col=1
    )
    fig1.add_trace(
        go.Bar(
            x=gex_by_strike["strike_price"],
            y=neg_gex,
            name="-GEX (Put Dealer Short Gamma $M)",
            width=bar_width_single,
            marker_color="rgba(255, 42, 133, 0.90)",
            marker_line=dict(color="#ff2a85", width=1.0),
            hovertemplate="Strike $%{x:.2f}<br>Net -GEX: $%{y:.2f}M<extra></extra>",
        ),
        row=2, col=1
    )

    # Clean, non-overlapping vertical reference lines (Spot on Row 1 badge, Max Pain on Row 2 badge)
    fig1.add_vline(x=spot_price, line_dash="dash", line_width=2.2, line_color="#00f5d4")
    fig1.add_annotation(
        x=spot_price, y=1.0, yref="y domain", xref="x",
        text=f"<b>Spot ${spot_price:.2f}</b>",
        showarrow=False, xanchor="left", yanchor="top", xshift=6, yshift=-4,
        bgcolor="rgba(8, 10, 20, 0.92)", bordercolor="#00f5d4", borderwidth=1, borderpad=4,
        font=dict(color="#00f5d4", size=11),
        row=1, col=1,
    )
    if max_pain:
        fig1.add_vline(x=max_pain, line_dash="dot", line_width=2.0, line_color="#ffbe0b")
        fig1.add_annotation(
            x=max_pain, y=1.0, yref="y2 domain", xref="x2",
            text=f"<b>Max Pain ${max_pain:.0f}</b>",
            showarrow=False, xanchor="right", yanchor="top", xshift=-6, yshift=-4,
            bgcolor="rgba(8, 10, 20, 0.92)", bordercolor="#ffbe0b", borderwidth=1, borderpad=4,
            font=dict(color="#ffbe0b", size=11),
        )

    fig1.update_layout(
        barmode="group",
        height=650,
        margin=dict(l=82, r=36, t=64, b=118),
        legend=dict(orientation="h", y=-0.16, yanchor="top", x=0.0, xanchor="left", font=dict(size=11.5)),
        **darkwave_layout,
    )
    fig1.update_xaxes(range=[focus_low, focus_high], automargin=True, gridcolor="rgba(0, 245, 212, 0.08)", zerolinecolor="rgba(0, 245, 212, 0.15)")
    fig1.update_xaxes(showticklabels=False, title_text="", row=1, col=1)
    fig1.update_yaxes(automargin=True, title_standoff=10, gridcolor="rgba(0, 245, 212, 0.08)", zerolinecolor="rgba(0, 245, 212, 0.25)")
    fig1.update_yaxes(title_text="Open Interest (Contracts)", row=1, col=1)
    fig1.update_yaxes(title_text="Net GEX ($M / 1%)", row=2, col=1)
    fig1.update_xaxes(showticklabels=True, title_text="Option Strike Price ($)", title_standoff=10, row=2, col=1)

    # 2. Smooth Liquidity-Weighted Implied Volatility Smile & Intraday Volume by Strike
    # Filter to valid, liquid IV observations and compute OI+Vol weighted IV per strike so multi-expiration chains don't create vertical sawtooth spikes
    iv_valid = df_clean[
        df_clean["implied_volatility"].notna()
        & (df_clean["implied_volatility"] > 0.02)
        & (df_clean["implied_volatility"] < 2.50)
        & ((df_clean["open_interest"] >= 5) | (df_clean["volume"] >= 1))
    ].copy()
    if iv_valid.empty:
        iv_valid = df_clean[df_clean["implied_volatility"].notna()].copy()

    def _smooth_iv_curve(sub_df: pd.DataFrame) -> pd.DataFrame:
        if sub_df.empty:
            return pd.DataFrame(columns=["strike_price", "iv_pct", "iv_smooth"])
        sub_df = sub_df.copy()
        sub_df["w_iv"] = sub_df["implied_volatility"] * sub_df["weight"]
        agg = sub_df.groupby("strike_price", as_index=False).agg(
            w_iv_sum=("w_iv", "sum"),
            w_sum=("weight", "sum"),
            oi=("open_interest", "sum"),
        ).sort_values("strike_price")
        agg["iv_pct"] = (agg["w_iv_sum"] / agg["w_sum"].clip(lower=1)) * 100.0
        # Filter out low-liquidity half-dollar strike outliers that have < 5% of neighbor OI
        if len(agg) > 12:
            med_oi = agg["oi"].median()
            liquid = agg[agg["oi"] >= max(5, med_oi * 0.10)]
            if len(liquid) >= 6:
                agg = liquid.copy()
        agg["iv_smooth"] = agg["iv_pct"].rolling(window=3, center=True, min_periods=1).median().rolling(window=3, center=True, min_periods=1).mean()
        return agg

    c_iv_curve = _smooth_iv_curve(iv_valid[iv_valid["contract_type"] == "call"])
    p_iv_curve = _smooth_iv_curve(iv_valid[iv_valid["contract_type"] == "put"])

    atm_iv_pct = f"{(summary.get('atm_iv') or 0) * 100:.1f}%" if summary.get("atm_iv") else "N/A"
    skew_pct = f"{(summary.get('iv_skew_25d') or 0) * 100:+.1f}%" if summary.get("iv_skew_25d") is not None else "N/A"
    fig2 = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.13,
        row_heights=[0.54, 0.46],
        subplot_titles=(
            f"{ticker} Liquidity-Weighted Implied Volatility Smile  •  ATM IV: {atm_iv_pct}  |  25Δ Put-Call Skew: {skew_pct}",
            f"{ticker} Intraday Options Volume by Strike (Calls vs Puts)"
        )
    )
    if not c_iv_curve.empty:
        fig2.add_trace(
            go.Scatter(
                x=c_iv_curve["strike_price"],
                y=c_iv_curve["iv_smooth"],
                mode="lines+markers",
                name="Call IV Smile (%)",
                line=dict(color="#00f5d4", width=2.6, shape="spline", smoothing=0.6),
                marker=dict(size=5, color="#00f5d4"),
                hovertemplate="Strike $%{x:.2f}<br>Call IV: %{y:.2f}%<extra></extra>",
            ),
            row=1, col=1
        )
    if not p_iv_curve.empty:
        fig2.add_trace(
            go.Scatter(
                x=p_iv_curve["strike_price"],
                y=p_iv_curve["iv_smooth"],
                mode="lines+markers",
                name="Put IV Smile (%)",
                line=dict(color="#ff2a85", width=2.6, shape="spline", smoothing=0.6),
                marker=dict(size=5, color="#ff2a85"),
                hovertemplate="Strike $%{x:.2f}<br>Put IV: %{y:.2f}%<extra></extra>",
            ),
            row=1, col=1
        )
    fig2.add_trace(
        go.Bar(
            x=calls["strike_price"],
            y=calls["volume"],
            name="Call Volume",
            width=bar_width_grouped,
            marker_color="rgba(0, 187, 249, 0.88)",
            marker_line=dict(color="#00bbf9", width=0.8),
            hovertemplate="Strike $%{x:.2f}<br>Call Vol: %{y:,}<extra></extra>",
        ),
        row=2, col=1
    )
    fig2.add_trace(
        go.Bar(
            x=puts["strike_price"],
            y=puts["volume"],
            name="Put Volume",
            width=bar_width_grouped,
            marker_color="rgba(247, 37, 133, 0.88)",
            marker_line=dict(color="#f72585", width=0.8),
            hovertemplate="Strike $%{x:.2f}<br>Put Vol: %{y:,}<extra></extra>",
        ),
        row=2, col=1
    )
    fig2.add_vline(x=spot_price, line_dash="dash", line_width=2.2, line_color="#00f5d4")
    fig2.add_annotation(
        x=spot_price, y=1.0, yref="y domain", xref="x",
        text=f"<b>Spot ${spot_price:.2f}</b>",
        showarrow=False, xanchor="left", yanchor="top", xshift=6, yshift=-4,
        bgcolor="rgba(8, 10, 20, 0.92)", bordercolor="#00f5d4", borderwidth=1, borderpad=4,
        font=dict(color="#00f5d4", size=11),
        row=1, col=1,
    )
    fig2.update_layout(
        barmode="group",
        height=640,
        margin=dict(l=82, r=36, t=64, b=118),
        legend=dict(orientation="h", y=-0.16, yanchor="top", x=0.0, xanchor="left", font=dict(size=11.5)),
        **darkwave_layout,
    )
    fig2.update_xaxes(range=[focus_low, focus_high], automargin=True, gridcolor="rgba(0, 245, 212, 0.08)", zerolinecolor="rgba(0, 245, 212, 0.15)")
    fig2.update_xaxes(showticklabels=False, title_text="", row=1, col=1)
    fig2.update_yaxes(automargin=True, title_standoff=10, gridcolor="rgba(0, 245, 212, 0.08)", zerolinecolor="rgba(0, 245, 212, 0.15)")
    fig2.update_yaxes(title_text="Implied Volatility (%)", row=1, col=1)
    fig2.update_yaxes(title_text="Contracts Traded", row=2, col=1)
    fig2.update_xaxes(showticklabels=True, title_text="Option Strike Price ($)", title_standoff=10, row=2, col=1)

    return {
        "oi_gex_chart": json.dumps(fig1, cls=PlotlyJSONEncoder),
        "iv_smile_chart": json.dumps(fig2, cls=PlotlyJSONEncoder),
    }


def fetch_options_chain_analytics(
    ticker: str,
    expiration_date: Optional[str] = None,
    strike_window_pct: float = 0.12,
    max_days_out: int = 45,
    max_pages: int = 4,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, str]]:
    """
    Pulls active options chain snapshot from Polygon `/v3/snapshot/options/{ticker}` around the current spot price,
    computes Put/Call OI & Volume ratios, Max Pain, Call/Put walls, ATM IV, 25-delta skew, and Dealer GEX/DEX.
    """
    ticker = validate_equity_ticker(ticker)
    # Get underlying price first so we filter strikes around the money (+/- strike_window_pct)
    snap_payload = _polygon_get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}")
    t_snap = snap_payload.get("ticker") or {}
    spot = (
        (t_snap.get("lastTrade") or {}).get("p")
        or (t_snap.get("day") or {}).get("c")
        or (t_snap.get("prevDay") or {}).get("c")
    )
    if not spot or spot <= 0:
        # Fallback: pull 1 option contract to read underlying_asset.price
        probe = _polygon_get(f"/v3/snapshot/options/{ticker}", {"limit": 1})
        probe_res = (probe.get("results") or [{}])[0]
        spot = (probe_res.get("underlying_asset") or {}).get("price") or 100.0
    spot = float(spot)

    low_strike = round(spot * (1.0 - strike_window_pct), 2)
    high_strike = round(spot * (1.0 + strike_window_pct), 2)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    max_exp_str = (datetime.now(timezone.utc) + timedelta(days=max_days_out)).strftime("%Y-%m-%d")

    params: Dict[str, Any] = {
        "strike_price.gte": low_strike,
        "strike_price.lte": high_strike,
        "limit": 250,
    }
    if expiration_date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(expiration_date)):
        params["expiration_date"] = str(expiration_date)
        exp_filter_label = str(expiration_date)
    else:
        params["expiration_date.gte"] = today_str
        params["expiration_date.lte"] = max_exp_str
        exp_filter_label = f"{today_str}_to_{max_exp_str}"

    raw_items: List[Dict[str, Any]] = []
    payload = _polygon_get(f"/v3/snapshot/options/{ticker}", params)
    raw_items.extend(payload.get("results") or [])

    pages = 1
    while payload.get("next_url") and pages < max_pages:
        pages += 1
        payload = _polygon_get(payload["next_url"])
        raw_items.extend(payload.get("results") or [])

    contracts: List[Dict[str, Any]] = []
    for item in raw_items:
        details = item.get("details") or {}
        day = item.get("day") or {}
        greeks = item.get("greeks") or {}
        quote = item.get("last_quote") or {}
        trade = item.get("last_trade") or {}
        und = item.get("underlying_asset") or {}

        c_type = str(details.get("contract_type") or "").lower()
        if c_type not in ("call", "put"):
            continue
        strike = details.get("strike_price")
        if strike is None:
            continue
        strike_f = float(strike)
        oi = int(item.get("open_interest") or 0)
        vol = int(day.get("volume") or 0)
        iv = item.get("implied_volatility")
        iv_f = float(iv) if (iv is not None and math.isfinite(float(iv)) and 0 < float(iv) < 15.0) else None
        delta = greeks.get("delta")
        gamma = greeks.get("gamma")
        theta = greeks.get("theta")
        vega = greeks.get("vega")
        delta_f = float(delta) if (delta is not None and math.isfinite(float(delta))) else None
        gamma_f = float(gamma) if (gamma is not None and math.isfinite(float(gamma))) else None
        theta_f = float(theta) if (theta is not None and math.isfinite(float(theta))) else None
        vega_f = float(vega) if (vega is not None and math.isfinite(float(vega))) else None

        # Dealer Gamma Exposure ($ per 1% underlying move) = OI * 100 * gamma * spot^2 * 0.01 * (+1 for call, -1 for put)
        sign = 1.0 if c_type == "call" else -1.0
        gex_dollars = (oi * 100.0 * (gamma_f or 0.0) * (spot ** 2) * 0.01 * sign) if gamma_f is not None else 0.0
        dex_dollars = (oi * 100.0 * (delta_f or 0.0) * spot) if delta_f is not None else 0.0

        if und.get("price") and float(und["price"]) > 0:
            spot = float(und["price"])

        contracts.append({
            "contract_ticker": details.get("ticker", ""),
            "contract_type": c_type,
            "expiration_date": details.get("expiration_date", ""),
            "strike_price": strike_f,
            "implied_volatility": iv_f,
            "open_interest": oi,
            "volume": vol,
            "bid": float(quote["bid"]) if quote.get("bid") is not None else None,
            "ask": float(quote["ask"]) if quote.get("ask") is not None else None,
            "midpoint": float(quote["midpoint"]) if quote.get("midpoint") is not None else None,
            "last_price": float(trade["price"]) if trade.get("price") is not None else (float(day["close"]) if day.get("close") is not None else None),
            "break_even_price": float(item["break_even_price"]) if item.get("break_even_price") is not None else None,
            "delta": delta_f,
            "gamma": gamma_f,
            "theta": theta_f,
            "vega": vega_f,
            "vwap": float(day["vwap"]) if day.get("vwap") is not None else None,
            "gex_dollars": gex_dollars,
            "dex_dollars": dex_dollars,
        })

    if not contracts:
        summary = {
            "ticker": ticker,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "underlying_price": spot,
            "expiration_filter": exp_filter_label,
            "contracts_count": 0,
            "total_call_oi": 0,
            "total_put_oi": 0,
            "put_call_oi_ratio": None,
            "total_call_vol": 0,
            "total_put_vol": 0,
            "put_call_vol_ratio": None,
            "atm_iv": None,
            "avg_call_iv": None,
            "avg_put_iv": None,
            "iv_skew_25d": None,
            "max_pain_strike": None,
            "call_wall_strike": None,
            "put_wall_strike": None,
            "net_delta_exposure": 0.0,
            "net_gamma_exposure": 0.0,
            "expirations": [],
            "top_active_contracts": [],
        }
        charts = build_options_charts(pd.DataFrame(), ticker, spot, summary)
        return summary, [], charts

    df = pd.DataFrame(contracts)
    calls_df = df[df["contract_type"] == "call"]
    puts_df = df[df["contract_type"] == "put"]

    total_call_oi = int(calls_df["open_interest"].sum())
    total_put_oi = int(puts_df["open_interest"].sum())
    pc_oi_ratio = round(total_put_oi / total_call_oi, 3) if total_call_oi > 0 else None

    total_call_vol = int(calls_df["volume"].sum())
    total_put_vol = int(puts_df["volume"].sum())
    pc_vol_ratio = round(total_put_vol / total_call_vol, 3) if total_call_vol > 0 else None

    # Call wall (strike with highest Call OI) and Put wall (strike with highest Put OI)
    call_wall = None
    if not calls_df.empty and total_call_oi > 0:
        cw_series = calls_df.groupby("strike_price")["open_interest"].sum()
        call_wall = float(cw_series.idxmax())

    put_wall = None
    if not puts_df.empty and total_put_oi > 0:
        pw_series = puts_df.groupby("strike_price")["open_interest"].sum()
        put_wall = float(pw_series.idxmax())

    max_pain = _calculate_max_pain(df)

    # ATM IV (contracts within 1.5% of spot)
    atm_df = df[(df["strike_price"] >= spot * 0.985) & (df["strike_price"] <= spot * 1.015)].dropna(subset=["implied_volatility"])
    atm_iv = round(float(atm_df["implied_volatility"].median()) * 100.0, 2) if not atm_df.empty else None

    avg_call_iv = round(float(calls_df["implied_volatility"].dropna().median()) * 100.0, 2) if not calls_df["implied_volatility"].dropna().empty else None
    avg_put_iv = round(float(puts_df["implied_volatility"].dropna().median()) * 100.0, 2) if not puts_df["implied_volatility"].dropna().empty else None

    # 25-delta Put-Call IV Skew (25d Put IV minus 25d Call IV in percentage points)
    puts_25d = puts_df[(puts_df["delta"] >= -0.35) & (puts_df["delta"] <= -0.15)].dropna(subset=["implied_volatility"])
    calls_25d = calls_df[(calls_df["delta"] >= 0.15) & (calls_df["delta"] <= 0.35)].dropna(subset=["implied_volatility"])
    if not puts_25d.empty and not calls_25d.empty:
        iv_skew_25d = round((float(puts_25d["implied_volatility"].median()) - float(calls_25d["implied_volatility"].median())) * 100.0, 2)
    elif avg_put_iv is not None and avg_call_iv is not None:
        iv_skew_25d = round(avg_put_iv - avg_call_iv, 2)
    else:
        iv_skew_25d = None

    net_dex = round(float(df["dex_dollars"].sum()), 2)
    net_gex = round(float(df["gex_dollars"].sum()), 2)
    expirations = sorted([e for e in df["expiration_date"].unique().tolist() if e])

    # Top active contracts by volume + OI
    df_sorted = df.sort_values(["volume", "open_interest"], ascending=[False, False]).head(30)
    top_contracts = []
    for row in df_sorted.to_dict(orient="records"):
        top_contracts.append({
            "contract_ticker": row["contract_ticker"],
            "contract_type": row["contract_type"],
            "expiration_date": row["expiration_date"],
            "strike_price": row["strike_price"],
            "implied_volatility_pct": round(row["implied_volatility"] * 100.0, 2) if row["implied_volatility"] is not None else None,
            "open_interest": row["open_interest"],
            "volume": row["volume"],
            "bid": row["bid"],
            "ask": row["ask"],
            "midpoint": row["midpoint"],
            "last_price": row["last_price"],
            "delta": round(row["delta"], 4) if row["delta"] is not None else None,
            "gamma": round(row["gamma"], 5) if row["gamma"] is not None else None,
            "theta": round(row["theta"], 4) if row["theta"] is not None else None,
            "vega": round(row["vega"], 4) if row["vega"] is not None else None,
            "gex_dollars": round(row["gex_dollars"], 0),
        })

    summary = {
        "ticker": ticker,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "underlying_price": round(spot, 2),
        "expiration_filter": exp_filter_label,
        "contracts_count": len(contracts),
        "total_call_oi": total_call_oi,
        "total_put_oi": total_put_oi,
        "put_call_oi_ratio": pc_oi_ratio,
        "total_call_vol": total_call_vol,
        "total_put_vol": total_put_vol,
        "put_call_vol_ratio": pc_vol_ratio,
        "atm_iv": atm_iv,
        "avg_call_iv": avg_call_iv,
        "avg_put_iv": avg_put_iv,
        "iv_skew_25d": iv_skew_25d,
        "max_pain_strike": max_pain,
        "call_wall_strike": call_wall,
        "put_wall_strike": put_wall,
        "net_delta_exposure": net_dex,
        "net_gamma_exposure": net_gex,
        "expirations": expirations,
        "top_active_contracts": top_contracts,
    }
    charts = build_options_charts(df, ticker, spot, summary)
    return summary, contracts, charts
