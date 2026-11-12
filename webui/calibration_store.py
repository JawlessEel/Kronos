"""Local, atomic store for matured Kronos forecast outcomes."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd


def load_calibration(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {'version': 1, 'series': {}}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data,dict) or data.get('version') != 1 or not isinstance(data.get('series'),dict):
            raise ValueError('invalid state structure')
        if any(not isinstance(rows,list) for rows in data['series'].values()):
            raise ValueError('invalid state series')
        return data
    except (OSError,ValueError,TypeError) as exc:
        raise RuntimeError(f'Cannot safely read Kronos calibration state: {path}') from exc


def save_calibration(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8') as file:
        json.dump(state,file,allow_nan=False,separators=(',',':'))
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp,path)


def update_actuals(records: list[dict[str, Any]], completed_bars: pd.DataFrame) -> int:
    """Fill missing outcomes only from candles already completed by the feed."""
    mapping={pd.Timestamp(t).tz_convert('UTC').isoformat():float(c)
             for t,c in zip(completed_bars['timestamps'],completed_bars['close'])}
    filled=0
    for record in records:
        actual=record.get('actual',[])
        for i, timestamp in enumerate(record.get('future',[])):
            if i>=len(actual) or actual[i] is not None:
                continue
            try:
                value=mapping.get(pd.Timestamp(timestamp).tz_convert('UTC').isoformat())
            except (TypeError,ValueError):
                continue
            if value is not None and value>0:
                actual[i]=value
                filled+=1
    return filled


def append_forecast(records: list[dict[str, Any]], record: dict[str, Any], *, limit: int = 180) -> None:
    """One forecast per actual decision time; retain a bounded rolling history."""
    records[:] = [r for r in records if r.get('decision') != record.get('decision')]
    records.append(record)
    records.sort(key=lambda r:r['decision'])
    del records[:-limit]


def artifact_signature(model_dir: Path, tokenizer_dir: Path) -> str:
    """Fingerprint the configs and weight files used to produce calibration."""
    digest=hashlib.sha256()
    for label,folder in (("model",model_dir),("tokenizer",tokenizer_dir)):
        files=sorted(p for p in folder.iterdir() if p.is_file() and (p.name=="config.json" or p.suffix in (".safetensors", ".bin")))
        if not any(p.suffix in (".safetensors", ".bin") for p in files):
            raise ValueError(f"No local weights found for {label}")
        for path in files:
            digest.update(f"{label}/{path.name}\0".encode())
            with path.open("rb") as source:
                for chunk in iter(lambda:source.read(8*1024*1024),b""):
                    digest.update(chunk)
    return digest.hexdigest()


def series_key(ticker: str, interval: int, lookback: int, samples: int, model: str,
               tokenizer: str = "Kronos-Tokenizer-base", signature: str = "unverified") -> str:
    return f'{ticker}|{interval}|{lookback}|{samples}|{model}|{tokenizer}|{signature}'


def future_availability(future: pd.Series, ticker: str, interval: int) -> list[str]:
    """Actual close availability for completed bars in the live feed."""
    from webui.polygon_feed import CALENDAR, is_crypto
    stamps=pd.Series(future).reset_index(drop=True)
    if interval == 1440 and not is_crypto(ticker):
        times=(stamps.dt.tz_convert('America/New_York')+pd.DateOffset(days=1)).dt.tz_convert('UTC')
    else:
        times=stamps.dt.tz_convert('UTC')+pd.Timedelta(minutes=interval)
    if interval == 60 and not is_crypto(ticker):
        schedule=CALENDAR.schedule(start_date=stamps.iloc[0].date(),end_date=stamps.iloc[-1].date())
        closes={d.date():row.market_close for d,row in schedule.iterrows()}
        times=pd.Series([min(end,closes[pd.Timestamp(start).tz_convert('America/New_York').date()])
                         for start,end in zip(stamps,times)])
    return [pd.Timestamp(t).isoformat() for t in times]
