"""Server-side Polygon candles and forecasts for US regular stock sessions."""
from datetime import timedelta
import json
import os
from pathlib import Path
import re
import threading
import time

from dotenv import dotenv_values
from flask import Blueprint, g, jsonify, request
import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder
import requests

ROOT = Path(__file__).resolve().parents[1]
CALENDAR = mcal.get_calendar("NYSE")
TZ = "America/New_York"
INTERVALS = (1, 5, 15)


class FeedError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def settings():
    private = dotenv_values(ROOT / ".env")
    key = os.environ.get("POLYGON_API_KEY") or private.get("POLYGON_API_KEY")
    base = (os.environ.get("POLYGON_BASE_URL") or private.get("POLYGON_BASE_URL") or "https://api.polygon.io").rstrip("/")
    if base not in ("https://api.polygon.io", "https://api.massive.com"):
        raise FeedError("Unsupported provider URL in server configuration.", 503)
    return key, base


def selection(ticker, interval):
    ticker = str(ticker).strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", ticker):
        raise FeedError("Enter a US stock/ETF symbol such as SPY or AAPL.")
    try:
        interval = int(interval)
    except (ValueError, TypeError):
        raise FeedError("Candle interval must be 1, 5, or 15 minutes.") from None
    if interval not in INTERVALS:
        raise FeedError("Candle interval must be 1, 5, or 15 minutes.")
    return ticker, interval


def normalize_bars(results, interval, now):
    """Discard unfinished and extended-hours bars without inventing missing candles."""
    if not results:
        raise FeedError("No candles returned. Check the symbol and your data subscription.", 422)
    try:
        df = pd.DataFrame(results).rename(columns={"t": "timestamps", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        df["timestamps"] = pd.to_datetime(df["timestamps"], unit="ms", utc=True)
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="raise")
        values = df[["open", "high", "low", "close", "volume"]]
        if not np.isfinite(values.to_numpy()).all() or (df["volume"] < 0).any() or (values.iloc[:, :4] <= 0).any().any():
            raise ValueError("Invalid values")
        if (df["high"] < values.iloc[:, :4].max(axis=1)).any() or (df["low"] > values.iloc[:, :4].min(axis=1)).any():
            raise ValueError("Invalid OHLC range")
        # Polygon's VWAP * share volume estimates dollar turnover, not a quote price.
        vwap = pd.to_numeric(df["vw"], errors="raise") if "vw" in df else df[["open", "high", "low", "close"]].mean(axis=1)
        if not np.isfinite(vwap).all() or (vwap <= 0).any():
            raise ValueError("Invalid VWAP")
        df["amount"] = vwap * df["volume"]
    except (KeyError, ValueError, TypeError, OverflowError):
        raise FeedError("Provider returned malformed candle data; no forecast was generated.", 502) from None
    df = df.sort_values("timestamps").drop_duplicates("timestamps", keep="last")
    schedule = CALENDAR.schedule(start_date=df["timestamps"].min().date(), end_date=df["timestamps"].max().date())
    keep = pd.Series(False, index=df.index)
    end = df["timestamps"] + pd.Timedelta(minutes=interval)
    for session in schedule.itertuples():
        keep |= (df["timestamps"] >= session.market_open) & (end <= session.market_close) & (end <= now)
    df = df.loc[keep, ["timestamps", "open", "high", "low", "close", "volume", "amount"]].tail(400).reset_index(drop=True)
    if len(df) < 400:
        raise FeedError(f"Only {len(df)} completed regular-session candles are available; 400 are required. Try another interval/symbol or check your subscription.", 422)
    df["timestamps"] = df["timestamps"].dt.tz_convert(TZ)
    return df


def future_timestamps(last, interval, count):
    """Use NYSE holidays, early closes and DST for the forecast calendar."""
    last = pd.Timestamp(last).tz_convert("UTC")
    schedule = CALENDAR.schedule(start_date=last.date(), end_date=last.date() + timedelta(days=60))
    times = []
    step = pd.Timedelta(minutes=interval)
    for session in schedule.itertuples():
        candidates = pd.date_range(session.market_open, session.market_close - step, freq=step)
        times.extend(candidates[candidates > last])
        if len(times) >= count:
            return pd.Series(pd.DatetimeIndex(times[:count]).tz_convert(TZ), name="timestamps")
    raise FeedError("Could not construct the future exchange calendar.", 422)


def metadata(df, ticker, interval, now, provider_status, fetched_at):
    today = now.tz_convert(TZ).date()
    schedule = CALENDAR.schedule(start_date=today, end_date=today)
    opened = bool(len(schedule) and schedule.iloc[0].market_open <= now < schedule.iloc[0].market_close)
    last = df["timestamps"].iloc[-1]
    return {"ticker": ticker, "interval_minutes": interval, "rows": len(df),
            "last_candle": last.isoformat(), "last_close": float(df["close"].iloc[-1]),
            "last_candle_age_seconds": round((now - last.tz_convert("UTC")).total_seconds()),
            "fetched_at": fetched_at.isoformat(), "market_open": opened,
            "provider_status": provider_status,
            "delay_notice": "Provider reports delayed data." if provider_status == "DELAYED" else "Recency depends on your Polygon subscription; an OK response does not certify real-time access.",
            "session": "US regular session only; completed candles; split-adjusted"}


def records(df):
    return [{"timestamp": row.timestamps.isoformat(), **{col: float(getattr(row, col)) for col in ("open", "high", "low", "close", "volume", "amount")}} for row in df.itertuples()]


def chart(df, ticker, forecast=None):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df["timestamps"], open=df.open, high=df.high, low=df.low, close=df.close, name="Polygon completed candles"))
    if forecast is not None:
        fig.add_trace(go.Candlestick(x=forecast.index, open=forecast.open, high=forecast.high, low=forecast.low, close=forecast.close, name="Kronos forecast", increasing_line_color="#1976d2", decreasing_line_color="#9c27b0"))
    fig.update_layout(title=f"{ticker}: completed candles" + (" and future forecast" if forecast is not None else ""), template="plotly_white", xaxis_rangeslider_visible=False, height=550, margin=dict(l=45, r=20, t=65, b=45), legend=dict(orientation="h", y=1.12), yaxis_title="Price (USD)")
    return json.dumps(fig, cls=PlotlyJSONEncoder)


class PolygonFeed:
    def __init__(self):
        self.lock = threading.Lock()
        self.cache = {}
        self.last_attempt = {}

    def candles(self, ticker, interval):
        ticker, interval = selection(ticker, interval)
        now = pd.Timestamp.now(tz="UTC")
        cache_key = (ticker, interval)
        with self.lock:
            cached = self.cache.get(cache_key)
            if cached and time.monotonic() - cached[3] < 60:
                df, status, fetched, _ = cached
                return df.copy(), metadata(df, ticker, interval, now, status, fetched)
            if time.monotonic() - self.last_attempt.get(cache_key, -1e9) < 60:
                raise FeedError("Wait 60 seconds before retrying this feed.", 429)
            key, base = settings()
            if not key:
                raise FeedError("Polygon key is missing from the server's private .env file.", 503)
            self.last_attempt[cache_key] = time.monotonic()
            url = f"{base}/v2/aggs/ticker/{ticker}/range/{interval}/minute/{(now - pd.Timedelta(days=30)).date()}/{now.date()}"
            try:
                response = requests.get(url, headers={"Authorization": f"Bearer {key}"}, params={"adjusted": "true", "sort": "desc", "limit": 50000}, timeout=(5, 30), allow_redirects=False)
            except requests.RequestException:
                raise FeedError("Polygon connection failed or timed out. Try again later.", 502) from None
            if response.status_code in (401, 403):
                raise FeedError("Polygon denied access. Check your API key and US stocks subscription entitlements.", response.status_code)
            if response.status_code == 429:
                raise FeedError("Polygon rate limit reached. Wait before refreshing.", 429)
            if response.status_code != 200:
                raise FeedError(f"Polygon returned HTTP {response.status_code}; no forecast was generated.", 502)
            try:
                payload = response.json()
            except ValueError:
                raise FeedError("Polygon returned an invalid response.", 502) from None
            if not isinstance(payload, dict):
                raise FeedError("Polygon returned an invalid response.", 502)
            status = payload.get("status")
            if status not in ("OK", "DELAYED"):
                raise FeedError("Polygon did not authorize usable candle data. Check the subscription.", 502)
            df = normalize_bars(payload.get("results"), interval, now)
            # Bound memory when symbols are changed frequently.
            if len(self.cache) >= 20:
                self.cache.clear()
                self.last_attempt = {cache_key: self.last_attempt[cache_key]}
            self.cache[cache_key] = (df, status, now, time.monotonic())
            return df.copy(), metadata(df, ticker, interval, now, status, now)


def register_live_feed(app, ui):
    feed = PolygonFeed()
    routes = Blueprint("polygon_live", __name__)
    inference_lock = threading.Lock()

    @app.before_request
    def guard_live_requests():
        if request.path.startswith("/api/live/"):
            if request.host.split(":")[0] not in ("127.0.0.1", "localhost") or request.headers.get("Sec-Fetch-Site") == "cross-site":
                return jsonify(error="Live feed requests must come from this local application."), 403
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                return jsonify(error="Live feed requests must come from this local application."), 403
        if request.path in ("/api/load-model", "/api/predict", "/api/live/predict"):
            if not inference_lock.acquire(blocking=False):
                return jsonify(error="The model is busy. Wait for the current operation."), 409
            g.kronos_inference_locked = True

    @app.teardown_request
    def unlock_inference(error):
        if getattr(g, "kronos_inference_locked", False):
            g.kronos_inference_locked = False
            inference_lock.release()

    @routes.errorhandler(FeedError)
    def feed_error(error):
        return jsonify(error=str(error)), error.status

    @routes.get("/api/live/status")
    def status():
        key, _ = settings()
        return jsonify(configured=bool(key), refresh_seconds=60, symbol="SPY", intervals=list(INTERVALS))

    @routes.get("/api/live/candles")
    def candles():
        df, info = feed.candles(request.args.get("ticker", "SPY"), request.args.get("interval", "5"))
        return jsonify(success=True, feed=info, candles=records(df), chart=chart(df, info["ticker"]))

    @routes.post("/api/live/predict")
    def predict():
        if ui.predictor is None:
            raise FeedError("Load a Kronos model using the Control Panel first.")
        args = request.get_json(silent=True) or {}
        ticker, interval = selection(args.get("ticker", "SPY"), args.get("interval", 5))
        try:
            count = int(args.get("pred_len", 30))
            temperature = float(args.get("temperature", 1.0))
            top_p = float(args.get("top_p", 0.9))
            samples = int(args.get("sample_count", 1))
        except (TypeError, ValueError):
            raise FeedError("Invalid forecast parameters.") from None
        if not (1 <= count <= 120 and 0.1 <= temperature <= 2 and 0 < top_p <= 1 and 1 <= samples <= 5):
            raise FeedError("Use 1–120 future candles, temperature 0.1–2, top-p above 0 up to 1, and 1–5 samples.")
        df, info = feed.candles(ticker, interval)
        future = future_timestamps(df["timestamps"].iloc[-1], interval, count)
        try:
            pred = ui.predictor.predict(df=df.drop(columns="timestamps"), x_timestamp=df["timestamps"], y_timestamp=future, pred_len=count, T=temperature, top_p=top_p, sample_count=samples, verbose=False)
        except Exception:
            # Request/credential details must never be reflected into the browser.
            raise FeedError("Kronos inference failed. Check model/device availability and retry.", 500) from None
        if not np.isfinite(pred.to_numpy()).all():
            raise FeedError("Kronos returned non-finite predictions; results were not saved.", 500)
        prediction = records(pred.reset_index(names="timestamps"))
        result = dict(success=True, feed=info, chart=chart(df, ticker, pred), prediction_results=prediction,
                      actual_data=[], has_comparison=False, forecast_anchor=info["last_candle"],
                      message=f"{ticker}: forecasted {count} candles after the latest available completed candle. No future actual prices are known.")
        output = ROOT / "outputs" / "live"
        try:
            output.mkdir(parents=True, exist_ok=True)
            stamp = pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%S%fZ")
            filename = f"{ticker}_{interval}min_{stamp}.json"
            (output / filename).write_text(json.dumps(result, indent=2), encoding="utf-8")
        except OSError:
            raise FeedError("Forecast completed but could not be saved. Check the project output folder.", 500) from None
        result["saved_file"] = filename
        return jsonify(result)

    app.register_blueprint(routes)
    return feed
