"""
Massive 5-Minute Intraday Multi-Ticker Dataset Ingestion Pipeline.
Uses https://api.massive.com (Polygon Massive Endpoint) to fetch multi-year, high-volume
candlestick datasets across liquid US equities and ETFs.
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
DATA_DIR = ROOT / "data" / "massive_5min"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Key US Equities & ETFs capturing broad indices, growth, small-caps, and mega-cap momentum
TARGET_TICKERS = ["SPY", "QQQ", "IWM", "NVDA", "AAPL", "MSFT", "TSLA"]

START_DATE = "2023-01-01"
END_DATE = "2024-11-30"
BASE_URL = "https://api.massive.com"

def get_api_key():
    key = os.environ.get("POLYGON_API_KEY") or dotenv_values(ROOT / ".env").get("POLYGON_API_KEY")
    if not key:
        raise RuntimeError("POLYGON_API_KEY not found in environment or .env file.")
    return key

def fetch_ticker_massive(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Fetch all 5-minute bars for a ticker across the date range using pagination."""
    key = get_api_key()
    out_file = DATA_DIR / f"{ticker}_5min_{start[:4]}_{end[:4]}.csv"
    
    if out_file.exists():
        print(f"[{ticker}] Cached file already exists: {out_file} (loading...)")
        df = pd.read_csv(out_file)
        return df

    print(f"\n[{ticker}] Fetching 5-minute bars from {start} to {end} via {BASE_URL}...")
    url = f"{BASE_URL}/v2/aggs/ticker/{ticker}/range/5/minute/{start}/{end}"
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
        print(f"  [{ticker}] Page {page_count}: received {len(results)} bars (Total accumulated: {len(all_rows):,})")
        
        next_url = payload.get("next_url")
        if not next_url:
            break
            
        time.sleep(0.15)  # respectful pacing

    if not all_rows:
        print(f"Warning: No data returned for {ticker}")
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
    print(f"[{ticker}] Complete! Saved {len(df):,} clean 5-minute bars to {out_file}")
    return df[cols]

def main():
    print("=" * 80)
    print("MASSIVE 5-MINUTE MULTI-TICKER INGESTION ENGINE")
    print(f"Provider Endpoint: {BASE_URL}")
    print(f"Target Range     : {START_DATE} to {END_DATE}")
    print(f"Tickers          : {', '.join(TARGET_TICKERS)}")
    print("=" * 80)

    summary_counts = {}
    for ticker in TARGET_TICKERS:
        try:
            df = fetch_ticker_massive(ticker, START_DATE, END_DATE)
            summary_counts[ticker] = len(df)
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            summary_counts[ticker] = 0

    print("\n" + "=" * 80)
    print("INGESTION COMPLETED SUMMARY")
    print("=" * 80)
    total_bars = sum(summary_counts.values())
    for t, cnt in summary_counts.items():
        print(f"  {t:8} : {cnt:10,d} 5-minute candles")
    print(f"  TOTAL    : {total_bars:10,d} candlesticks acquired across all tickers!")
    print(f"All files saved under: {DATA_DIR}")

if __name__ == "__main__":
    main()
