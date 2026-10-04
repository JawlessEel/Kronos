"""Server-side Polygon candles and forecasts for stocks and USD crypto pairs."""
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
from webui.forecast_settings import validate_forecast, history_length

ROOT = Path(__file__).resolve().parents[1]
CALENDAR = mcal.get_calendar("NYSE")
TZ = "America/New_York"
INTERVALS = (1, 5, 15, 60, 240, 1440)


def is_crypto(ticker):
    return ticker.startswith('X:')


def provider_interval(ticker, interval):
    if interval == 1440:
        return 1, 'day'
    if interval >= 60:
        return (interval // 60, 'hour') if is_crypto(ticker) else (30, 'minute')
    return interval, 'minute'


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
    if not re.fullmatch(r"(?:[A-Z][A-Z0-9.\-]{0,14}|X:[A-Z0-9]{2,20}USD)", ticker):
        raise FeedError("Enter a US stock/ETF symbol (SPY) or USD crypto pair (X:BTCUSD, X:ETHUSD).")
    try:
        interval = int(interval)
    except (ValueError, TypeError):
        raise FeedError("Choose 1m, 5m, 15m, 1h, 4h, or 1d candles.") from None
    if interval not in INTERVALS:
        raise FeedError("Choose 1m, 5m, 15m, 1h, 4h, or 1d candles.")
    return ticker, interval


def normalize_bars(results, interval, now, count=400, ticker='SPY'):
    """Keep completed market-specific bars without inventing missing candles."""
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
    crypto = is_crypto(ticker)
    if crypto or interval == 1440:
        if crypto:
            completed = df['timestamps'] + pd.Timedelta(minutes=interval) <= now
        else:
            # Provider stock daily bars span the ET calendar date, including
            # eligible extended-hours trades. Wait until that day is finished.
            local = df['timestamps'].dt.tz_convert(TZ)
            completed = (local + pd.DateOffset(days=1)).dt.tz_convert('UTC') <= now
        df = df.loc[completed]
    else:
        df = regular_bars(df, interval, now)
    df = df.loc[:, ["timestamps", "open", "high", "low", "close", "volume", "amount"]].tail(count).reset_index(drop=True)
    if len(df) < count:
        raise FeedError(f"Only {len(df)} completed candles are available; {count} are required. Try less history, another timeframe/symbol, or check your subscription.", 422)
    df["timestamps"] = df["timestamps"].dt.tz_convert('UTC' if crypto else TZ)
    return df


def regular_bars(df, interval, now):
    schedule = CALENDAR.schedule(start_date=df["timestamps"].min().date(), end_date=df["timestamps"].max().date())
    keep = pd.Series(False, index=df.index)
    base_interval = 30 if interval >= 60 else interval
    end = df["timestamps"] + pd.Timedelta(minutes=base_interval)
    for session in schedule.itertuples():
        keep |= (df["timestamps"] >= session.market_open) & (end <= session.market_close) & (end <= now)
    df = df.loc[keep]
    if interval < 60:
        return df
    rows = []
    # Build regular-session 1h/4h bars from provider 30m bars, anchored at
    # 09:30 ET. The final bar ends at actual close, including early closes.
    for session in schedule.itertuples():
        for start in pd.date_range(session.market_open, session.market_close, freq=f'{interval}min', inclusive='left'):
            finish = min(start + pd.Timedelta(minutes=interval), session.market_close)
            if finish > now:
                continue
            group = df.loc[(df.timestamps >= start) & (df.timestamps < finish)]
            expected = pd.date_range(start, finish, freq='30min', inclusive='left')
            if list(group.timestamps) != list(expected):
                continue  # Never fill missing traded bars or incomplete history pages.
            rows.append(dict(timestamps=start, open=group.open.iloc[0], high=group.high.max(), low=group.low.min(), close=group.close.iloc[-1], volume=group.volume.sum(), amount=group.amount.sum()))
    return pd.DataFrame(rows, columns=df.columns)


def future_timestamps(last, interval, count, ticker='SPY'):
    """Use NYSE holidays, early closes and DST for the forecast calendar."""
    last = pd.Timestamp(last).tz_convert("UTC")
    if is_crypto(ticker):
        return pd.Series(pd.date_range(last + pd.Timedelta(minutes=interval), periods=count, freq=f'{interval}min'), name='timestamps')
    schedule = CALENDAR.schedule(start_date=last.date(), end_date=last.date() + timedelta(days=max(365, count * 2)))
    times = []
    step = pd.Timedelta(minutes=interval)
    for session in schedule.itertuples():
        if interval == 1440:
            candidates = pd.DatetimeIndex([session.market_open.tz_convert(TZ).normalize().tz_convert('UTC')])
        elif interval >= 60:
            candidates = pd.date_range(session.market_open, session.market_close, freq=step, inclusive='left')
        else:
            candidates = pd.date_range(session.market_open, session.market_close - step, freq=step)
        times.extend(candidates[candidates > last])
        if len(times) >= count:
            return pd.Series(pd.DatetimeIndex(times[:count]).tz_convert(TZ), name="timestamps")
    raise FeedError("Could not construct the future exchange calendar.", 422)


def metadata(df, ticker, interval, now, provider_status, fetched_at):
    today = now.tz_convert(TZ).date()
    schedule = CALENDAR.schedule(start_date=today, end_date=today)
    opened = bool(len(schedule) and schedule.iloc[0].market_open <= now < schedule.iloc[0].market_close)
    crypto = is_crypto(ticker)
    last = df["timestamps"].iloc[-1]
    return {"ticker": ticker, "interval_minutes": interval, "rows": len(df),
            "last_candle": last.isoformat(), "last_close": float(df["close"].iloc[-1]),
            "last_candle_age_seconds": round((now - last.tz_convert("UTC")).total_seconds()),
            "fetched_at": fetched_at.isoformat(), "market_open": True if crypto else opened,
            "market": 'crypto' if crypto else 'stocks', "timezone": 'UTC' if crypto else TZ,
            "session": 'Crypto 24/7; completed UTC candles' if crypto else 'Provider daily stock bars; completed ET days; eligible extended-hours trades included' if interval == 1440 else 'US regular session only; completed candles; split-adjusted; final hourly bar may be shorter',
            "provider_status": provider_status,
            "delay_notice": "Provider reports delayed data." if provider_status == "DELAYED" else "Recency depends on your Polygon subscription; an OK response does not certify real-time access.",
            }


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

    def candles(self, ticker, interval, count=400):
        ticker, interval = selection(ticker, interval)
        now = pd.Timestamp.now(tz="UTC")
        count = history_length(count)
        cache_key = (ticker, interval, count)
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
            multiplier, timespan = provider_interval(ticker, interval)
            days = min(365 * 30, max(365, count * (2 if interval == 1440 else 1 if interval == 240 else 0.25)))
            url = f"{base}/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{(now - pd.Timedelta(days=days)).date()}/{now.date()}"
            try:
                response = requests.get(url, headers={"Authorization": f"Bearer {key}"}, params={"adjusted": "true", "sort": "desc", "limit": 50000}, timeout=(5, 30), allow_redirects=False)
            except requests.RequestException:
                raise FeedError("Polygon connection failed or timed out. Try again later.", 502) from None
            if response.status_code in (401, 403):
                raise FeedError(f"Polygon denied access. Check your API key and {'crypto' if is_crypto(ticker) else 'US stocks'} subscription entitlements.", response.status_code)
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
            all_rows = payload.get("results") or []
            # Polygon limits underlying minute aggregates per page. Follow only
            # same-provider aggregate pages, never credentials from next_url.
            from urllib.parse import urlsplit, parse_qsl
            for _ in range(12):
                try:
                    df = normalize_bars(all_rows, interval, now, count, ticker)
                    break
                except FeedError as error:
                    if error.status != 422 or not payload.get("next_url"):
                        raise
                next_page = urlsplit(payload["next_url"])
                if next_page.scheme != "https" or next_page.netloc != urlsplit(base).netloc or not next_page.path.startswith(f"/v2/aggs/ticker/{ticker}/range/"):
                    raise FeedError("Provider returned an invalid pagination URL.", 502)
                try:
                    page = requests.get(base + next_page.path, headers={"Authorization": f"Bearer {key}"}, params={k: v for k, v in parse_qsl(next_page.query) if k.lower() != "apikey"}, timeout=(5, 30), allow_redirects=False)
                    if page.status_code != 200:
                        raise FeedError(f"Provider history page returned HTTP {page.status_code}.", 502)
                    payload = page.json()
                    if not isinstance(payload, dict) or payload.get("status") not in ("OK", "DELAYED"):
                        raise FeedError("Provider history page is invalid.", 502)
                    if payload.get("status") == "DELAYED":
                        status = "DELAYED"
                    all_rows.extend(payload.get("results") or [])
                except (requests.RequestException, ValueError):
                    raise FeedError("Provider history request failed.", 502) from None
            else:
                raise FeedError("Requested history exceeds the bounded provider page budget. Reduce chart history.", 422)
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
            authenticated = app.config.get('KRONOS_AUTHENTICATED', False)
            if (not authenticated and request.host.split(":")[0] not in ("127.0.0.1", "localhost")) or request.headers.get("Sec-Fetch-Site") == "cross-site":
                return jsonify(error="Live feed requests must come from this local application."), 403
            origin = request.headers.get("Origin")
            expected_origin = request.host_url.rstrip("/").replace('http://', 'https://', 1) if authenticated else request.host_url.rstrip("/")
            if origin and origin != expected_origin:
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
        return jsonify(configured=bool(key), refresh_seconds=60, symbol="SPY", intervals=list(INTERVALS), models={k: v["context_length"] for k, v in getattr(ui, "AVAILABLE_MODELS", {}).items()}, loaded_context=getattr(ui.predictor, "max_context", None))

    @routes.errorhandler(ValueError)
    def invalid_setting(error):
        return jsonify(error="Invalid chart history; use 16-10,000 candles."), 400

    @routes.get("/api/live/candles")
    def candles():
        df, info = feed.candles(request.args.get("ticker", "SPY"), request.args.get("interval", "5"), request.args.get("history", "400"))
        return jsonify(success=True, feed=info, candles=records(df), chart=chart(df, info["ticker"]))

    @routes.post("/api/live/predict")
    def predict():
        if ui.predictor is None:
            raise FeedError("Load a Kronos model using the Control Panel first.")
        args = request.get_json(silent=True) or {}
        ticker, interval = selection(args.get("ticker", "SPY"), args.get("interval", 5))
        if args.get('target_today') is True and (is_crypto(ticker) or interval not in (1, 5, 15)):
            raise FeedError('Watch through-close targets support US stocks with 1m, 5m or 15m candles. Use a candle-count forecast for crypto and longer timeframes.', 422)
        try:
            count = int(args.get("pred_len", 30))
            lookback = int(args.get("lookback", 400))
            history = history_length(args.get("history", lookback))
            temperature = float(args.get("temperature", 1.0))
            top_p = float(args.get("top_p", 0.9))
            samples = int(args.get("sample_count", 1))
        except (TypeError, ValueError):
            raise FeedError("Invalid forecast parameters.") from None
        try:
            validate_forecast(ui.predictor, lookback, count, temperature, top_p, samples)
        except ValueError as error:
            raise FeedError(str(error)) from None
        df, info = feed.candles(ticker, interval, max(history, lookback))
        model_df = df.tail(lookback)
        if args.get('target_today') is True:
            from webui.watch_summary import remaining_session_times
            try:
                future = remaining_session_times(df['timestamps'].iloc[-1], interval, pd.Timestamp.now(tz='UTC'))
            except ValueError as error:
                raise FeedError(str(error), 422) from None
            count = len(future)
            try:
                validate_forecast(ui.predictor, lookback, count, temperature, top_p, samples)
            except ValueError as error:
                raise FeedError(str(error)) from None
        else:
            future = future_timestamps(df["timestamps"].iloc[-1], interval, count, ticker)
        try:
            pred = ui.predictor.predict(df=model_df.drop(columns="timestamps"), x_timestamp=model_df["timestamps"], y_timestamp=future, pred_len=count, T=temperature, top_p=top_p, sample_count=samples, verbose=False)
        except Exception:
            # Request/credential details must never be reflected into the browser.
            raise FeedError("Kronos inference failed. Check model/device availability and retry.", 500) from None
        if len(pred) != count or not np.isfinite(pred.to_numpy()).all():
            raise FeedError("Kronos returned non-finite predictions; results were not saved.", 500)
        prediction = records(pred.reset_index(names="timestamps"))
        result = dict(success=True, generated_at=pd.Timestamp.now(tz='UTC').isoformat(), feed=info, chart=chart(df, ticker, pred), prediction_results=prediction,
                      candles=records(df), settings=dict(lookback=lookback, pred_len=count, sample_count=samples, temperature=temperature, top_p=top_p), actual_data=[], has_comparison=False, forecast_anchor=info["last_candle"],
                      message=f"{ticker}: forecasted {count} candles after the latest available completed candle. No future actual prices are known.")
        output = ROOT / "outputs" / "live"
        try:
            output.mkdir(parents=True, exist_ok=True)
            stamp = pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%S%fZ")
            filename = f"{ticker.replace(':', '-')}_{interval}min_{stamp}.json"
            (output / filename).write_text(json.dumps(result, indent=2), encoding="utf-8")
        except OSError:
            raise FeedError("Forecast completed but could not be saved. Check the project output folder.", 500) from None
        result["saved_file"] = filename
        return jsonify(result)

    app.register_blueprint(routes)
    from webui.watch_summary import register_watch_summary
    register_watch_summary(app, ROOT / 'outputs' / 'live')
    return feed
