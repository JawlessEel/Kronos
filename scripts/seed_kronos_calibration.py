#!/usr/bin/env python3
"""Seed local calibration with completed scheduled walk-forward forecasts."""
from __future__ import annotations
import argparse
import fcntl
import json
import sys
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from webui.calibration_store import append_forecast, artifact_signature, load_calibration, save_calibration, series_key  # noqa: E402


def merge_matured(report, state, now):
    now=pd.Timestamp(now)
    if now.tzinfo is None:
        raise ValueError('Seed cutoff must have a timezone')
    count=0
    samples=int(report['method']['samples']); lookback=int(report['method']['lookback'])
    for group in report['results']:
        if group.get('error') or len(group.get('records',[])) < 12:
            raise ValueError('Every series must have at least 12 valid evaluation origins')
        key=series_key(group['ticker'],group['interval_minutes'],lookback,samples,'Kronos-small', signature=report['method'].get('artifact_signature','unverified'))
        rows=state['series'].setdefault(key,[])
        for item in group['records']:
            if not item.get('actual') or any(x is None for x in item['actual']):
                continue
            if any(pd.Timestamp(t).tz_convert('UTC') > now.tz_convert('UTC') for t in item['available']):
                continue
            if not any(r.get('decision')==item['decision'] for r in rows):
                append_forecast(rows,item)
                count+=1
    return count


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--bot-lock',type=Path,required=True)
    args=parser.parse_args()
    report=json.loads(args.input.read_text(encoding='utf-8'))
    signature=artifact_signature(ROOT/'models/Kronos-small',ROOT/'models/Kronos-Tokenizer-base')
    if report.get('method',{}).get('artifact_signature') != signature:
        raise SystemExit('Evaluation model/tokenizer fingerprint is missing or differs from installed files')
    groups=report.get('results',[])
    expected={(ticker,interval) for ticker in ('SPY','X:BTCUSD') for interval in (5,15,60,1440)}
    if len(groups) != 8 or {(g.get('ticker'),g.get('interval_minutes')) for g in groups} != expected:
        raise SystemExit('Refusing to seed an incomplete eight-series evaluation')
    args.bot_lock.parent.mkdir(parents=True,exist_ok=True)
    with args.bot_lock.open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Bot is delivering Kronos predictions; retry seeding later')
        try:
            state=load_calibration(args.state)
            added=merge_matured(report,state,pd.Timestamp.now(tz='UTC'))
            save_calibration(args.state,state)
        finally:
            fcntl.flock(lock,fcntl.LOCK_UN)
    print(f'Seeded {added} matured forecasts across {len(state["series"])} series.')


if __name__=='__main__':
    main()
