"""
20-Year Multi-Timeframe SPY Dataset Ingestion Pipeline.
Queries https://api.massive.com for SPY spanning 2004 to 2024 across multiple timeframes:
- 5-minute
- 15-minute
- 1-hour
- 1-day (Daily)
"""
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl
import pandas as pd
import requests
from dotenv import dotenv_values

ROOT = Path("/Volumes/MacMoneyMakerSSD/Ai_apps/kronos")
DATA_DIR = ROOT / "data" / "spy_multi_timeframe"
DATA_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = "2004-01-01"
END_DATE = "2024-11-30"
BASE_URL = "https://api.massive.com"

TIMEFRAMES = [
    {"name": "5min", "mult": 5, "span": "minute"},
    {"name": "15min", "mult": 15, "span": "minute"},
    {"name": "1hour", "mult": 1, "span": "hour"},
    {"name": "1day", "mult": 1, "span": "day"},
]

def get_api_key():
    key = os.environ.get("POLYGON_API_KEY") or dotenv_values(ROOT / ".env").get("POLYGON_API_KEY")
    if not key:
        raise RuntimeError("POLYGON_API_KEY not found in environment or .env file.")
    return key

def fetch_timeframe(name: str, mult: int, span: str, start: str, end: str) -> pd.DataFrame:
    key = get_api_key()
    out_file = DATA_DIR / f"SPY_{name}_{start[:4]}_{end[:4]}.csv"

    if out_file.exists():
        print(f"[{name}] Cached file exists: {out_file} (loading...)")
        df = pd.read_csv(out_file)
        print(f"[{name}] Loaded {len(df):,} bars from cache.")
        return df

    print(f"\n========================================================")
    print(f"[SPY {name}] Fetching {mult}-{span} bars from {start} to {end}...")
    print(f"========================================================")
    
    url = f"{BASE_URL}/v2/aggs/ticker/SPY/range/{mult}/{span}/{start}/{end}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000}

    all_rows = []
    page_count = 0
    next_url = None

    while True:
        page_count += 1
        if next_url:
            parsed = urlsplit(next_url)
            query_params = {k: v for k, v in parse_qsl(parsed.query) if k.lower() != "apikey"}
            req_url = BASE_URL + parsed.path
            response = requests.get(req_url, headers={"Authorization": f"Bearer {key}"}, params=query_params, timeout=30)
        else:
            response = requests.get(url, headers={"Authorization": f"Bearer {key}"}, params=params, timeout=30)

        if response.status_code != 200:
            raise RuntimeError(f"API request failed with HTTP {response.status_code}: {response.text}")

        payload = response.json()
        results = payload.get("results", [])
        if not results:
            break

        all_rows.extend(results)
        print(f"  [{name}] Page {page_count}: received {len(results):,} bars (Accumulated: {len(all_rows):,})")

        next_url = payload.get("next_url")
        if not next_url:
            break

        time.sleep(0.12)  # respectful pacing

    if not all_rows:
        print(f"Warning: No data returned for SPY {name}")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows).rename(columns={
        "t": "timestamps", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"
    })
    df["timestamps"] = pd.to_datetime(df["timestamps"], unit="ms", utc=True)

    if "vw" in df:
        df["amount"] = df["vw"] * df["volume"]
    else:
        df["amount"] = df[["open", "high", "low", "close"]].mean(axis=1) * df["volume"]

    cols = ["timestamps", "open", "close", "high", "low", "volume", "amount"]
    df = df.sort_values("timestamps").drop_duplicates("timestamps").reset_index(drop=True)
    df["timestamps"] = df["timestamps"].dt.strftime("%Y-%m-%d %H:%M:%S")

    df[cols].to_csv(out_file, index=False)
    print(f"[{name}] Successfully saved {len(df):,} clean bars to {out_file}")
    return df[cols]

def main():
    print("=" * 80)
    print("SPY 20-YEAR MULTI-TIMEFRAME DATASET INGESTION")
    print(f"Range: {START_DATE} to {END_DATE}")
    print(f"Destination: {DATA_DIR}")
    print("=" * 80)

    summary = {}
    for tf in TIMEFRAMES:
        df = fetch_timeframe(tf["name"], tf["mult"], tf["span"], START_DATE, END_DATE)
        summary[tf["name"]] = len(df)

    print("\n" + "=" * 80)
    print("INGESTION SUMMARY:")
    total = 0
    for name, count in summary.items():
        print(f"  SPY {name:<10}: {count:>10,} bars")
        total += count
    print(f"  TOTAL BARS   : {total:>10,} bars across 2004-2024")
    print("=" * 80)

if __name__ == "__main__":
    main()
