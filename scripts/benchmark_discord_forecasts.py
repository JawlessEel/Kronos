#!/usr/bin/env python3
"""Walk-forward comparison of Discord Kronos settings against no change.

Uses real completed Polygon bars and generated exchange-calendar timestamps.
Each test origin has 400 prior bars, and the actual forecast bars are never
passed as model inputs. Model paths are stochastic; intervals are uncalibrated.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_discord_forecast import DEFAULT_PRED_LEN, _load_predictor  # noqa: E402
from webui.polygon_feed import PolygonFeed, future_timestamps  # noqa: E402


def origins(df: pd.DataFrame, ticker: str, interval: int, horizon: int, count: int):
    """Select date-spread, non-overlapping origins with aligned future bars."""
    indices = []
    earliest = pd.Timestamp('2025-01-01', tz='UTC')
    for idx in range(399, len(df) - horizon, horizon):
        if df.timestamps.iloc[idx].tz_convert('UTC') < earliest:
            continue
        indices.append(idx)
    if len(indices) > count:
        indices = [indices[i] for i in np.linspace(0, len(indices)-1, count, dtype=int)]
    for idx in indices:
        hist = df.iloc[idx-399:idx+1].reset_index(drop=True)
        actual = df.iloc[idx+1:idx+1+horizon].reset_index(drop=True)
        future = future_timestamps(hist.timestamps.iloc[-1], interval, horizon, ticker)
        if pd.DatetimeIndex(future).equals(pd.DatetimeIndex(actual.timestamps)):
            yield hist, actual, future


def score(records, key):
    if not records:
        return {}
    errors = [abs(r[key] - r['actual']) / r['start'] * 100 for r in records]
    naive = [abs(r['start'] - r['actual']) / r['start'] * 100 for r in records]
    hits = sum(int(np.sign(r[key]-r['start']) == np.sign(r['actual']-r['start'])) for r in records)
    return {'mae_pct': float(np.mean(errors)), 'baseline_mae_pct': float(np.mean(naive)),
            'direction_correct': hits, 'beat_no_change': sum(int(a < b) for a,b in zip(errors,naive))}


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--windows', type=int, default=30)
    parser.add_argument('--samples', type=int, default=5)
    parser.add_argument('--batch-origins', type=int, default=2)
    parser.add_argument('--out', default=str(ROOT/'outputs/reliability'/f"walk_forward_{pd.Timestamp.now(tz='UTC'):%Y%m%dT%H%M%SZ}.json"))
    args = parser.parse_args()
    if args.windows < 1 or not 2 <= args.samples <= 20 or args.batch_origins < 1:
        parser.error('windows and batch origins must be positive; samples must be 2–20')
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    feed = PolygonFeed()
    predictor, device = _load_predictor(ROOT/'models/Kronos-small', ROOT/'models/Kronos-Tokenizer-base')
    report = {'method': {'lookback': 400, 'windows_requested': args.windows, 'samples': args.samples,
              'temperatures': [1.0, 0.6], 'top_p': 0.9, 'minimum_asof': '2025-01-01',
              'baseline': 'unchanged last close', 'bands': '10th–90th percentile of sampled closes; uncalibrated',
              'device': device}, 'results': []}
    for ticker in ('SPY', 'X:BTCUSD'):
        for interval in (5,15,60,1440):
            begin = time.monotonic(); horizon = DEFAULT_PRED_LEN[interval]
            try:
                requested = 900 if interval == 1440 else (4000 if interval == 60 else 7500)
                df, info = feed.candles(ticker, interval, count=requested)
                selected = list(origins(df,ticker,interval,horizon,args.windows))
                records = []
                print(f'{ticker} {interval}m: {len(selected)} aligned origins, {len(df)} bars', flush=True)
                for first in range(0,len(selected),args.batch_origins):
                    group = selected[first:first+args.batch_origins]
                    data = [h.drop(columns='timestamps') for h,a,f in group for _ in range(args.samples)]
                    xs = [h.timestamps for h,a,f in group for _ in range(args.samples)]
                    ys = [f for h,a,f in group for _ in range(args.samples)]
                    paths_by_temp = []
                    for temp_index, temp in enumerate((1.0,0.6)):
                        torch.manual_seed(20261112 + interval * 1000 + first * 2 + temp_index + (1 if ticker=='SPY' else 10000000))
                        paths_by_temp.append(predictor.predict_batch(data,xs,ys,horizon,T=temp,top_p=0.9,sample_count=1,verbose=False))
                    for group_index,(hist,actual,future) in enumerate(group):
                        values = [np.array([float(p.close.iloc[-1]) for p in group_paths[group_index*args.samples:(group_index+1)*args.samples]]) for group_paths in paths_by_temp]
                        r = {'asof':hist.timestamps.iloc[-1].isoformat(), 'end':actual.timestamps.iloc[-1].isoformat(),
                             'start':float(hist.close.iloc[-1]),'actual':float(actual.close.iloc[-1]),
                             'current':float(values[0][0]), 'mean_t1':float(values[0].mean()), 'mean_t06':float(values[1].mean()),
                             't1_samples':values[0].tolist(), 't06_samples':values[1].tolist()}
                        records.append(r)
                    if (first//args.batch_origins)%5 == 0:
                        print(f'  {ticker} {interval}m: {len(records)}/{len(selected)} origins',flush=True)
                summaries={name:score(records,name) for name in ('current','mean_t1','mean_t06')}
                for name, sample_key in (('mean_t1','t1_samples'),('mean_t06','t06_samples')):
                    cover = [int(np.quantile(r[sample_key],.1) <= r['actual'] <= np.quantile(r[sample_key],.9)) for r in records]
                    summaries[name]['interval_coverage'] = sum(cover)
                result={'ticker':ticker,'interval_minutes':interval,'horizon_bars':horizon,'provider_status':info.get('provider_status'),
                        'windows':len(records),'first_asof':records[0]['asof'] if records else None,
                        'last_end':records[-1]['end'] if records else None,'scores':summaries,'records':records,
                        'seconds':round(time.monotonic()-begin,1)}
                report['results'].append(result); out.write_text(json.dumps(report,indent=2),encoding='utf-8')
                print(json.dumps({k:v for k,v in result.items() if k!='records'}),flush=True)
            except Exception as exc:
                report['results'].append({'ticker':ticker,'interval_minutes':interval,'error':f'{type(exc).__name__}: {exc}'})
                out.write_text(json.dumps(report,indent=2),encoding='utf-8')
                print(f'{ticker} {interval}m error: {type(exc).__name__}: {exc}',flush=True)
    return 0 if all('error' not in x and x.get('windows',0) > 0 for x in report['results']) else 1


if __name__ == '__main__':
    raise SystemExit(run())
