"""
Multi-Asset, Multi-Season, Multi-Timeframe Historical Data Loader for Kronos Research.
Caches downloaded Polygon bars locally to avoid rate limits and ensure deterministic backtesting.
Supports automatic pagination for high-granularity intraday series.
"""
import os
import json
import time
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl
import pandas as pd
import requests
from dotenv import dotenv_values

ROOT = Path("/Volumes/MacMoneyMakerSSD/Ai_apps/kronos")
CACHE_DIR = ROOT / "data" / "research_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def get_polygon_key():
    key = os.environ.get("POLYGON_API_KEY") or dotenv_values(ROOT / ".env").get("POLYGON_API_KEY")
    if not key:
        raise RuntimeError("POLYGON_API_KEY is not configured in .env")
    return key

def fetch_polygon_bars(ticker: str, multiplier: int, timespan: str, from_date: str, to_date: str) -> pd.DataFrame:
    """Fetch candlestick data from Polygon with pagination and local disk caching."""
    clean_ticker = ticker.replace(":", "_")
    cache_file = CACHE_DIR / f"{clean_ticker}_{multiplier}{timespan}_{from_date}_{to_date}.csv"
    if cache_file.exists():
        df = pd.read_csv(cache_file)
        df["timestamps"] = pd.to_datetime(df["timestamps"], utc=True)
        return df

    key = get_polygon_key()
    base_url = "https://api.polygon.io"
    url = f"{base_url}/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000}
    
    response = requests.get(url, headers={"Authorization": f"Bearer {key}"}, params=params, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Polygon API returned HTTP {response.status_code}: {response.text}")
    
    payload = response.json()
    all_results = list(payload.get("results", []))
    
    # Paginate if more data exists
    page_count = 0
    while payload.get("next_url") and page_count < 10:
        page_count += 1
        next_parsed = urlsplit(payload["next_url"])
        next_params = {k: v for k, v in parse_qsl(next_parsed.query) if k.lower() != "apikey"}
        next_page = requests.get(
            base_url + next_parsed.path,
            headers={"Authorization": f"Bearer {key}"},
            params=next_params,
            timeout=30
        )
        if next_page.status_code != 200:
            break
        payload = next_page.json()
        new_batch = payload.get("results", [])
        if not new_batch:
            break
        all_results.extend(new_batch)
        time.sleep(0.1)

    if not all_results:
        raise RuntimeError(f"No bars returned for {ticker} between {from_date} and {to_date}")
        
    df = pd.DataFrame(all_results).rename(columns={
        "t": "timestamps", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"
    })
    df["timestamps"] = pd.to_datetime(df["timestamps"], unit="ms", utc=True)
    
    if "vw" in df:
        df["amount"] = df["vw"] * df["volume"]
    else:
        df["amount"] = df[["open", "high", "low", "close"]].mean(axis=1) * df["volume"]
        
    df = df[["timestamps", "open", "high", "low", "close", "volume", "amount"]].sort_values("timestamps").drop_duplicates("timestamps").reset_index(drop=True)
    df.to_csv(cache_file, index=False)
    return df
