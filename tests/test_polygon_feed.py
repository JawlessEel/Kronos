from types import SimpleNamespace

from flask import Flask
import numpy as np
import pandas as pd
import pytest
import requests

from webui import polygon_feed as live


def market_rows():
    schedule = live.CALENDAR.schedule("2026-09-01", "2026-10-02")
    rows = []
    for session in schedule.itertuples():
        # Include premarket and an unfinished last candle to test filtering.
        for stamp in pd.date_range(session.market_open - pd.Timedelta(minutes=5), session.market_close - pd.Timedelta(minutes=5), freq="5min"):
            rows.append(dict(t=int(stamp.timestamp() * 1000), o=100, h=102, l=99, c=101, v=10, vw=100.5))
    return rows


def test_mapping_sorting_turnover_and_unfinished_bar():
    now = pd.Timestamp("2026-10-02T19:58:00Z")
    df = live.normalize_bars(list(reversed(market_rows())), 5, now)
    assert len(df) == 400
    assert df.timestamps.is_monotonic_increasing
    assert str(df.timestamps.dt.tz) == "America/New_York"
    assert df.timestamps.iloc[-1] == pd.Timestamp("2026-10-02T15:50:00-04:00")
    assert df.amount.eq(1005).all()
    assert df.timestamps.dt.hour.ge(9).all()


@pytest.mark.parametrize("last,first", [
    ("2026-07-02T15:55:00-04:00", "2026-07-06T09:30:00-04:00"),
    ("2026-11-27T12:55:00-05:00", "2026-11-30T09:30:00-05:00"),
    ("2026-10-30T15:55:00-04:00", "2026-11-02T09:30:00-05:00"),
])
def test_forecast_calendar_holiday_early_close_dst(last, first):
    future = live.future_timestamps(last, 5, 30)
    assert len(future) == 30
    assert future.iloc[0] == pd.Timestamp(first)
    assert (future > pd.Timestamp(last)).all()


def test_malformed_candles_fail():
    rows = market_rows()
    rows[-1]["h"] = 50
    with pytest.raises(live.FeedError, match="malformed"):
        live.normalize_bars(rows, 5, pd.Timestamp("2026-10-04T12:00:00Z"))


def test_cache_and_server_only_authorization(monkeypatch):
    calls = []
    monkeypatch.setattr(live, "settings", lambda: ("test-private-key", "https://api.polygon.io"))
    monkeypatch.setattr(live.pd.Timestamp, "now", lambda **kwargs: pd.Timestamp("2026-10-04T12:00:00Z"))

    def get(url, **kwargs):
        assert "test-private-key" not in url
        assert kwargs["headers"]["Authorization"] == "Bearer test-private-key"
        assert kwargs["params"]["sort"] == "desc"
        assert kwargs["allow_redirects"] is False
        calls.append(url)
        return SimpleNamespace(status_code=200, json=lambda: {"status": "DELAYED", "results": market_rows()})

    monkeypatch.setattr(live.requests, "get", get)
    feed = live.PolygonFeed()
    first, info = feed.candles("spy", 5)
    second, _ = feed.candles("SPY", 5)
    assert len(calls) == 1
    assert len(first) == len(second) == 400
    assert info["provider_status"] == "DELAYED"
    assert not info["market_open"]
    assert "test-private-key" not in str(info)


def test_network_error_does_not_reflect_credentials(monkeypatch):
    monkeypatch.setattr(live, "settings", lambda: ("test-private-key", "https://api.polygon.io"))

    def fail(*args, **kwargs):
        raise requests.ConnectionError("URL contained test-private-key")

    monkeypatch.setattr(live.requests, "get", fail)
    with pytest.raises(live.FeedError) as result:
        live.PolygonFeed().candles("SPY", 5)
    assert "test-private-key" not in str(result.value)


def test_live_endpoint_uses_only_history_and_future_calendar(monkeypatch, tmp_path):
    df = live.normalize_bars(market_rows(), 5, pd.Timestamp("2026-10-04T12:00:00Z"))
    info = live.metadata(df, "SPY", 5, pd.Timestamp("2026-10-04T12:00:00Z"), "OK", pd.Timestamp("2026-10-04T12:00:00Z"))
    monkeypatch.setattr(live, "ROOT", tmp_path)
    monkeypatch.setattr(live.PolygonFeed, "candles", lambda self, ticker, interval, count=400: (df.copy(), info))

    class Predictor:
        def predict(self, **kwargs):
            assert len(kwargs["df"]) == 400
            assert kwargs["x_timestamp"].iloc[-1] == df.timestamps.iloc[-1]
            assert (kwargs["y_timestamp"] > kwargs["x_timestamp"].iloc[-1]).all()
            return pd.DataFrame(np.ones((kwargs["pred_len"], 6)) * 100, index=kwargs["y_timestamp"], columns=["open", "high", "low", "close", "volume", "amount"])

    app = Flask(__name__)
    live.register_live_feed(app, SimpleNamespace(predictor=Predictor()))
    client = app.test_client()
    response = client.post("/api/live/predict", json={"ticker": "SPY", "interval": 5, "pred_len": 30})
    result = response.get_json()
    assert response.status_code == 200
    assert len(result["prediction_results"]) == 30
    assert result["actual_data"] == []
    assert result["has_comparison"] is False
    assert len(list((tmp_path / "outputs" / "live").glob("*.json"))) == 1
    assert client.get("/api/live/candles", headers={"Origin": "https://other.example"}).status_code == 403
    assert client.get("/api/live/candles", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get("/api/live/candles", base_url="http://other.example").status_code == 403
    assert client.post("/api/live/predict", json={"pred_len": 0}).status_code == 400


@pytest.mark.parametrize("ticker,interval", [("../.env", 5), ("C:XAUUSD", 5), ("SPY", 30)])
def test_invalid_selection(ticker, interval):
    with pytest.raises(live.FeedError):
        live.selection(ticker, interval)


@pytest.mark.parametrize("code", [401, 403, 429, 500])
def test_provider_denial_and_rate_limit_are_explicit(monkeypatch, code):
    monkeypatch.setattr(live, "settings", lambda: ("test-private-key", "https://api.polygon.io"))
    monkeypatch.setattr(live.requests, "get", lambda *args, **kwargs: SimpleNamespace(status_code=code))
    with pytest.raises(live.FeedError) as result:
        live.PolygonFeed().candles("SPY", 5)
    assert result.value.status == (code if code in (401, 403, 429) else 502)
    assert "test-private-key" not in str(result.value)


def test_history_pagination_keeps_credentials_in_header(monkeypatch):
    monkeypatch.setattr(live, "settings", lambda: ("test-private-key", "https://api.polygon.io"))
    monkeypatch.setattr(live.pd.Timestamp, "now", lambda **kwargs: pd.Timestamp("2026-10-04T12:00:00Z"))
    rows = market_rows()
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        assert "test-private-key" not in url
        assert "apiKey" not in kwargs['params']
        assert kwargs['headers']['Authorization'] == 'Bearer test-private-key'
        payload = {'status':'OK', 'results':rows[-100:], 'next_url':'https://api.polygon.io/v2/aggs/ticker/SPY/range/5/minute/page?cursor=abc&apiKey=discard-me'} if len(calls) == 1 else {'status':'OK','results':rows[:-100]}
        return SimpleNamespace(status_code=200,json=lambda:payload)
    monkeypatch.setattr(live.requests, 'get', get)
    df, info = live.PolygonFeed().candles('SPY',5,1000)
    assert len(calls) == 2 and len(df) == 1000
    assert info['rows'] == 1000


def test_external_history_pagination_rejected(monkeypatch):
    monkeypatch.setattr(live, 'settings', lambda: ('test-private-key','https://api.polygon.io'))
    monkeypatch.setattr(live.requests, 'get', lambda *args,**kwargs: SimpleNamespace(status_code=200,json=lambda:{'status':'OK','results':market_rows()[-100:],'next_url':'https://other.example/v2/aggs/ticker/SPY/range/page'}))
    with pytest.raises(live.FeedError, match='pagination URL'):
        live.PolygonFeed().candles('SPY',5,1000)
