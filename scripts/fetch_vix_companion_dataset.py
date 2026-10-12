"""
Multi-Timeframe VIX Companion Dataset Ingestion Pipeline.
Queries https://api.massive.com for:
- VIXY (2011-01-01 to 2024-11-30) across 5m, 15m, 1h, 1d
- UVXY (2011-10-01 to 2024-11-30) across 5m, 15m, 1h, 1d
- I:VIX (2023-01-01 to 2024-11-30) across 5m, 15m, 1h, 1d
"""
import os
import time
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl
import numpy as np
import pandas as pd
import requests
from dotenv import dotenv_values

ROOT = Path("/Volumes/MacMoneyMakerSSD/Ai_apps/kronos")
DATA_DIR = ROOT / "data" / "vix_companion"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://api.massive.com"

ASSETS = [
    {"symbol": "VIXY", "clean_name": "VIXY", "start": "2011-01-03", "end": "2024-11-30"},
    {"symbol": "UVXY", "clean_name": "UVXY", "start": "2011-10-04", "end": "2024-11-30"},
    {"symbol": "I:VIX", "clean_name": "INDEX_VIX", "start": "2023-01-01", "end": "2024-11-30"},
]

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

def fetch_asset_timeframe(symbol: str, clean_name: str, tf_name: str, mult: int, span: str, start: str, end: str) -> pd.DataFrame:
    key = get_api_key()
    out_file = DATA_DIR / f"{clean_name}_{tf_name}_{start[:4]}_{end[:4]}.csv"

    if out_file.exists():
        df = pd.read_csv(out_file)
        print(f"[{clean_name} {tf_name}] Loaded {len(df):,} bars from cache: {out_file.name}")
        return df

    print(f"\n[{clean_name} {tf_name}] Fetching {mult}-{span} bars ({start} to {end})...")
    url = f"{BASE_URL}/v2/aggs/ticker/{symbol}/range/{mult}/{span}/{start}/{end}"
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
            raise RuntimeError(f"API request failed for {symbol} with HTTP {response.status_code}: {response.text}")

        payload = response.json()
        results = payload.get("results", [])
        if not results:
            break

        all_rows.extend(results)
        print(f"  [{clean_name} {tf_name}] Page {page_count}: +{len(results):,} bars (Total: {len(all_rows):,})")

        next_url = payload.get("next_url")
        if not next_url:
            break

        time.sleep(0.12)

    if not all_rows:
        print(f"Warning: No data returned for {symbol} {tf_name}")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows).rename(columns={
        "t": "timestamps", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"
    })
    df["timestamps"] = pd.to_datetime(df["timestamps"], unit="ms", utc=True)

    # Handle indices like I:VIX that lack direct trade volume
    if "volume" not in df or df["volume"].isnull().all() or (df["volume"] == 0).all():
        # Synthesize non-degenerate activity proxy from intrabar volatility range + close change
        bar_range = (df["high"] - df["low"]).abs() + (df["close"].diff().abs().fillna(0.01)) + 0.01
        df["volume"] = (bar_range * 10000.0).round(2)
        df["amount"] = (df["volume"] * df[["open", "high", "low", "close"]].mean(axis=1)).round(4)
    else:
        df["volume"] = df["volume"].fillna(0.0)
        if "vw" in df:
            df["amount"] = df["vw"].fillna(df["close"]) * df["volume"]
        else:
            df["amount"] = df[["open", "high", "low", "close"]].mean(axis=1) * df["volume"]

    cols = ["timestamps", "open", "close", "high", "low", "volume", "amount"]
    df = df.sort_values("timestamps").drop_duplicates("timestamps").reset_index(drop=True)
    df["timestamps"] = df["timestamps"].dt.strftime("%Y-%m-%d %H:%M:%S")

    df[cols].to_csv(out_file, index=False)
    print(f"[{clean_name} {tf_name}] Saved {len(df):,} clean bars -> {out_file.name}")
    return df[cols]

def main():
    print("=" * 80)
    print("VIX COMPANION MULTI-TIMEFRAME DATASET INGESTION")
    print(f"Destination: {DATA_DIR}")
    print("=" * 80)

    summary = {}
    for asset in ASSETS:
        for tf in TIMEFRAMES:
            key_name = f"{asset['clean_name']}_{tf['name']}"
            df = fetch_asset_timeframe(
                asset["symbol"], asset["clean_name"],
                tf["name"], tf["mult"], tf["span"],
                asset["start"], asset["end"]
            )
            summary[key_name] = len(df)

    print("\n" + "=" * 80)
    print("VIX COMPANION INGESTION SUMMARY:")
    total = 0
    for k, count in summary.items():
        print(f"  {k:<20}: {count:>10,} bars")
        total += count
    print(f"  TOTAL VIX BARS      : {total:>10,} bars")
    print("=" * 80)

if __name__ == "__main__":
    main()
