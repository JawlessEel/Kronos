#!/usr/bin/env python3
"""Generate Kronos multi-timeframe (5m, 15m, 60m, 1d) forecasts and dark-theme
EMA63/EMA200 charts for Discord delivery."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import Kronos, KronosPredictor, KronosTokenizer  # noqa: E402
from webui.polygon_feed import PolygonFeed, future_timestamps, is_crypto  # noqa: E402

TIMEFRAME_LABELS: dict[int, str] = {
    5: "5m",
    15: "15m",
    60: "1h",
    1440: "1d",
}

DEFAULT_PRED_LEN: dict[int, int] = {
    5: 24,
    15: 24,
    60: 18,
    1440: 10,
}


def _select_device() -> str:
    if torch.cuda.is_available():
        return "cuda:0"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _load_predictor(model_dir: Path, tokenizer_dir: Path, max_context: int = 512) -> tuple[KronosPredictor, str]:
    device = _select_device()
    tokenizer = KronosTokenizer.from_pretrained(str(tokenizer_dir))
    model = Kronos.from_pretrained(str(model_dir))
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=max_context)
    return predictor, device


def _display_ticker(ticker: str) -> str:
    if ticker == "X:BTCUSD":
        return "BTC-USD"
    if ticker.startswith("X:"):
        return ticker[2:]
    return ticker


def _plot_panel(
    ax: plt.Axes,
    hist_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    ticker: str,
    interval: int,
    visible_bars: int = 96,
) -> dict[str, Any]:
    tf_label = TIMEFRAME_LABELS.get(interval, f"{interval}m")

    # Compute 63 EMA and 200 EMA on full history (400 bars) so EMAs are warmed up.
    hist = hist_df.copy().reset_index(drop=True)
    hist["ema63"] = hist["close"].ewm(span=63, adjust=False).mean()
    hist["ema200"] = hist["close"].ewm(span=200, adjust=False).mean()

    # Continue EMAs smoothly through the forecast horizon for visual context.
    combined_close = pd.concat([hist["close"], pred_df["close"].reset_index(drop=True)], ignore_index=True)
    ema63_all = combined_close.ewm(span=63, adjust=False).mean()
    ema200_all = combined_close.ewm(span=200, adjust=False).mean()

    hist_tail = hist.tail(visible_bars).reset_index(drop=True)
    n_hist = len(hist_tail)
    n_pred = len(pred_df)

    pred_ema63 = ema63_all.iloc[len(hist) :].reset_index(drop=True)
    pred_ema200 = ema200_all.iloc[len(hist) :].reset_index(drop=True)

    # Use sequential integer x-axis so market-closed gaps don't distort candles.
    x_hist = np.arange(n_hist, dtype=float)
    x_pred = np.arange(n_hist, n_hist + n_pred, dtype=float)

    ax.set_facecolor("#161b22")
    ax.grid(True, color="#262c36", linestyle="--", linewidth=0.6, alpha=0.75)

    # Shade forecast region
    ax.axvspan(n_hist - 0.5, n_hist + n_pred - 0.5, color="#1f2937", alpha=0.45, zorder=0)
    ax.axvline(n_hist - 0.5, color="#64748b", linestyle="--", linewidth=1.0, zorder=2)

    # Plot historical candlesticks
    bar_w = 0.62
    for idx, row in hist_tail.iterrows():
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        color = "#26a69a" if c >= o else "#ef5350"
        ax.plot([idx, idx], [l, h], color=color, linewidth=0.9, zorder=3)
        body_bottom = min(o, c)
        body_h = max(abs(c - o), (h - l) * 0.02 or 1e-6)
        ax.add_patch(
            Rectangle((idx - bar_w / 2, body_bottom), bar_w, body_h, facecolor=color, edgecolor=color, linewidth=0.6, zorder=4)
        )

    # Plot Kronos forecast candlesticks
    pred_reset = pred_df.reset_index(drop=True)
    for j, row in pred_reset.iterrows():
        x = n_hist + j
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        color = "#38bdf8" if c >= o else "#a855f7"
        ax.plot([x, x], [l, h], color=color, linewidth=0.9, alpha=0.95, zorder=3)
        body_bottom = min(o, c)
        body_h = max(abs(c - o), (h - l) * 0.02 or 1e-6)
        ax.add_patch(
            Rectangle((x - bar_w / 2, body_bottom), bar_w, body_h, facecolor=color, edgecolor=color, linewidth=0.6, alpha=0.9, zorder=4)
        )

    # Plot 63 EMA and 200 EMA
    last_ema63 = float(hist_tail["ema63"].iloc[-1])
    last_ema200 = float(hist_tail["ema200"].iloc[-1])
    ax.plot(x_hist, hist_tail["ema63"], color="#f59e0b", linewidth=1.6, label=f"63 EMA ({last_ema63:,.2f})", zorder=5)
    ax.plot(x_hist, hist_tail["ema200"], color="#ec4899", linewidth=1.6, label=f"200 EMA ({last_ema200:,.2f})", zorder=5)

    # Dashed continuation of EMAs across forecast window
    ax.plot(
        np.concatenate([[x_hist[-1]], x_pred]),
        np.concatenate([[last_ema63], pred_ema63.to_numpy()]),
        color="#f59e0b",
        linewidth=1.2,
        linestyle=":",
        alpha=0.85,
        zorder=5,
    )
    ax.plot(
        np.concatenate([[x_hist[-1]], x_pred]),
        np.concatenate([[last_ema200], pred_ema200.to_numpy()]),
        color="#ec4899",
        linewidth=1.2,
        linestyle=":",
        alpha=0.85,
        zorder=5,
    )

    last_close = float(hist_tail["close"].iloc[-1])
    pred_end_close = float(pred_reset["close"].iloc[-1])
    pct_delta = ((pred_end_close - last_close) / last_close) * 100.0 if last_close else 0.0
    delta_sign = "+" if pct_delta >= 0 else ""

    ema_bias = "Bullish (63 > 200)" if last_ema63 > last_ema200 else "Bearish (63 < 200)"
    ax.set_title(
        f"{_display_ticker(ticker)} · {tf_label}  |  Last: {last_close:,.2f} → Pred: {pred_end_close:,.2f} ({delta_sign}{pct_delta:.2f}%)  |  {ema_bias}",
        color="#e6edf3",
        fontsize=10.5,
        fontweight="bold",
        loc="left",
        pad=8,
    )

    # Sparse readable time ticks
    all_ts = list(hist_tail["timestamps"]) + list(pred_df.index)
    tick_step = max(1, len(all_ts) // 6)
    tick_positions = list(range(0, len(all_ts), tick_step))
    if (n_hist - 1) not in tick_positions:
        tick_positions.append(n_hist - 1)
    tick_positions = sorted(set(tick_positions))
    fmt = "%m-%d" if interval >= 1440 else "%m-%d %H:%M"
    tick_labels = [pd.Timestamp(all_ts[i]).strftime(fmt) for i in tick_positions]

    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, color="#9ca3af", fontsize=8)
    ax.tick_params(axis="y", colors="#9ca3af", labelsize=8.5)
    for spine in ax.spines.values():
        spine.set_color("#30363d")

    leg = ax.legend(loc="upper left", frameon=True, facecolor="#0d1117", edgecolor="#30363d", fontsize=8.5)
    for text in leg.get_texts():
        text.set_color("#e6edf3")

    return {
        "timeframe": tf_label,
        "interval_minutes": interval,
        "last_candle": pd.Timestamp(hist_tail["timestamps"].iloc[-1]).isoformat(),
        "last_close": round(last_close, 4),
        "pred_end_time": pd.Timestamp(pred_df.index[-1]).isoformat(),
        "pred_end_close": round(pred_end_close, 4),
        "pred_delta_pct": round(pct_delta, 3),
        "pred_high": round(float(pred_reset["high"].max()), 4),
        "pred_low": round(float(pred_reset["low"].min()), 4),
        "ema63": round(last_ema63, 4),
        "ema200": round(last_ema200, 4),
        "ema_cross_state": "above" if last_ema63 > last_ema200 else "below",
        "pred_len": n_pred,
    }


def generate_ticker_forecast(
    feed: PolygonFeed,
    predictor: KronosPredictor,
    ticker: str,
    intervals: list[int],
    out_dir: Path,
    lookback: int,
    slot_label: str,
) -> dict[str, Any]:
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), dpi=150)
    fig.patch.set_facecolor("#0d1117")
    flat_axes = list(axes.flat)

    summaries: list[dict[str, Any]] = []
    for idx, interval in enumerate(intervals[:4]):
        pred_len = DEFAULT_PRED_LEN.get(interval, 24)
        hist_df, info = feed.candles(ticker, interval, count=lookback)
        model_df = hist_df.tail(lookback)
        future = future_timestamps(hist_df["timestamps"].iloc[-1], interval, pred_len, ticker)
        pred_df = predictor.predict(
            df=model_df.drop(columns="timestamps"),
            x_timestamp=model_df["timestamps"],
            y_timestamp=future,
            pred_len=pred_len,
            T=1.0,
            top_p=0.9,
            sample_count=1,
            verbose=False,
        )
        panel_summary = _plot_panel(flat_axes[idx], hist_df, pred_df, ticker, interval)
        panel_summary["provider_status"] = info.get("provider_status") or "UNKNOWN"
        summaries.append(panel_summary)

    now_et = pd.Timestamp.now(tz="America/New_York")
    disp = _display_ticker(ticker)
    fig.suptitle(
        f"Kronos Multi-Timeframe Forecast · {disp} ({slot_label}) · {now_et:%Y-%m-%d %H:%M ET}",
        color="#f0f6fc",
        fontsize=14,
        fontweight="bold",
        y=0.97,
    )
    fig.text(
        0.5,
        0.012,
        "Candles: Green/Red = Completed Polygon Bars | Cyan/Purple = Kronos Forecast | Amber = 63 EMA | Pink = 200 EMA | Advisory readout only.",
        ha="center",
        color="#8b949e",
        fontsize=9,
    )
    plt.tight_layout(rect=[0.01, 0.03, 0.99, 0.94])

    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = disp.replace(":", "-")
    chart_path = out_dir / f"{safe_name}_kronos_multi_tf.png"
    fig.savefig(chart_path, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)

    return {
        "ticker": ticker,
        "display_ticker": disp,
        "chart_path": str(chart_path),
        "timeframes": summaries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Kronos multi-timeframe forecasts for Discord")
    parser.add_argument("--tickers", default="SPY,X:BTCUSD", help="Comma-separated tickers")
    parser.add_argument("--intervals", default="5,15,60,1440", help="Comma-separated intervals in minutes")
    parser.add_argument("--lookback", type=int, default=400, help="Historical candle lookback (min 200 for EMA200)")
    parser.add_argument("--slot", default="Scheduled", help="Schedule slot label")
    parser.add_argument("--model-dir", default=str(ROOT / "models" / "Kronos-small"), help="Kronos model path")
    parser.add_argument("--tokenizer-dir", default=str(ROOT / "models" / "Kronos-Tokenizer-base"), help="Kronos tokenizer path")
    parser.add_argument("--out-dir", default=str(ROOT / "outputs" / "discord"), help="Output directory for PNG charts")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    intervals = [int(x.strip()) for x in args.intervals.split(",") if x.strip()]
    out_dir = Path(args.out_dir)

    predictor, device = _load_predictor(Path(args.model_dir), Path(args.tokenizer_dir), max_context=512)
    feed = PolygonFeed()

    results = []
    for ticker in tickers:
        results.append(
            generate_ticker_forecast(
                feed=feed,
                predictor=predictor,
                ticker=ticker,
                intervals=intervals,
                out_dir=out_dir,
                lookback=max(args.lookback, 250),
                slot_label=args.slot,
            )
        )

    payload = {
        "success": True,
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "device": device,
        "model": Path(args.model_dir).name,
        "slot": args.slot,
        "results": results,
    }
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
