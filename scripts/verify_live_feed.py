"""Verify the running local server with real Polygon data and real Kronos inference."""
import json
from pathlib import Path
import time

from dotenv import dotenv_values
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:7070"


def call(path, payload=None):
    response = requests.get(BASE + path, timeout=45) if payload is None else requests.post(BASE + path, json=payload, timeout=120)
    if response.status_code != 200:
        raise RuntimeError(f"Local endpoint {path} failed with HTTP {response.status_code}: {response.json().get('error', 'unknown error')}")
    private_key = dotenv_values(ROOT / ".env").get("POLYGON_API_KEY")
    if private_key:
        assert private_key not in response.text, "A private credential was exposed in the response."
    return response.json()


def main():
    assert call("/api/live/status")["configured"]
    candles = call("/api/live/candles?ticker=SPY&interval=5")
    assert len(candles["candles"]) == 400
    timestamps = pd.to_datetime([bar["timestamp"] for bar in candles["candles"]], utc=True)
    assert timestamps.is_monotonic_increasing and timestamps.is_unique
    call("/api/load-model", {"model_key": "kronos-base", "device": "cuda"})
    started = time.perf_counter()
    forecast = call("/api/live/predict", {"ticker": "SPY", "interval": 5, "pred_len": 30, "temperature": 1.0, "top_p": 0.9, "sample_count": 1})
    seconds = round(time.perf_counter() - started, 2)
    assert len(forecast["prediction_results"]) == 30
    assert forecast["actual_data"] == [] and not forecast["has_comparison"]
    predicted_times = pd.to_datetime([bar["timestamp"] for bar in forecast["prediction_results"]], utc=True)
    assert (predicted_times > timestamps[-1]).all()
    assert all(np.isfinite(bar[col]) for bar in forecast["prediction_results"] for col in ("open", "high", "low", "close"))
    assert (ROOT / "outputs" / "live" / forecast["saved_file"]).is_file()
    # The shared model lock must leave the original historical workflow working.
    sample = ROOT / "data" / "HK_ali_09988_kline_5min_all.csv"
    legacy = call("/api/predict", {"file_path": str(sample), "lookback": 400, "pred_len": 8, "start_date": "2019-11-26T09:35"})
    assert len(legacy["prediction_results"]) == len(legacy["actual_data"]) == 8
    report = dict(feed=candles["feed"], forecast_rows=30, forecast_seconds=seconds,
                  first_forecast=forecast["prediction_results"][0]["timestamp"],
                  saved_forecast=forecast["saved_file"], historical_workflow="passed", credentials_in_responses=False)
    (ROOT / "outputs" / "live-feed-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
