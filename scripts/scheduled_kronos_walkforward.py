#!/usr/bin/env python3
"""Point-in-time Kronos evaluation at real scheduled US market posting times.

The test rotates equally through the three posting times, one per NYSE session.
Inputs contain only bars completed by that posting time. Historical targets are
read only after inference; their availability time is recorded per horizon step.
Output contains sampled model paths for causal, delayed-outcome calibration.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import numpy as np
import pandas as pd
import requests
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_discord_forecast import DEFAULT_PRED_LEN, _load_predictor  # noqa: E402
from webui.polygon_feed import CALENDAR, FeedError, future_timestamps, is_crypto, normalize_bars, provider_interval, settings  # noqa: E402
from webui.calibration_store import artifact_signature  # noqa: E402
from webui.btc_daily_research import daily_volatility  # noqa: E402

ET = 'America/New_York'
TEMPERATURES = (1.0, 0.9, 0.8)
DEFAULT_TIMES = ('09:30', '12:00', '15:00')


def market_slots(now: pd.Timestamp, sessions: int, maturity_sessions: int = 12):
    """One date-spread real slot per NYSE session, balanced over configured times."""
    now = pd.Timestamp(now).tz_convert('UTC')
    schedule = CALENDAR.schedule(start_date=(now - pd.Timedelta(days=365)).date(), end_date=now.date())
    schedule = schedule.loc[schedule.market_open <= now]
    eligible = schedule.iloc[-(sessions + maturity_sessions):-maturity_sessions]
    slots = []
    for i, (day, row) in enumerate(eligible.iterrows()):
        ordered = DEFAULT_TIMES[i % 3:] + DEFAULT_TIMES[:i % 3]
        for hm in ordered:
            hour, minute = map(int, hm.split(':'))
            decision = pd.Timestamp(day.date(), tz=ET).replace(hour=hour, minute=minute).tz_convert('UTC')
            if row.market_open <= decision < row.market_close:
                slots.append(decision)
                break
    return slots


def load_history(ticker: str, interval: int, count: int):
    """Use the live feed's provider rules and normalizer, with longer history."""
    key, base = settings()
    if not key:
        raise FeedError('Polygon credential is unavailable', 503)
    now = pd.Timestamp.now(tz='UTC')
    days = 1200 if interval == 1440 else 365
    mult, span = provider_interval(ticker, interval)
    url = f'{base}/v2/aggs/ticker/{ticker}/range/{mult}/{span}/{(now-pd.Timedelta(days=days)).date()}/{now.date()}'
    params = {'adjusted':'true', 'sort':'desc', 'limit':50000}
    rows = []; statuses = []
    for page in range(15):
        response = requests.get(url, headers={'Authorization':f'Bearer {key}'}, params=params,
                                timeout=(5,30), allow_redirects=False)
        if response.status_code != 200:
            raise FeedError(f'Polygon history request returned HTTP {response.status_code}',response.status_code)
        payload = response.json()
        status = payload.get('status')
        if status not in ('OK','DELAYED'):
            raise FeedError('Polygon returned unusable history status',502)
        statuses.append(status); rows.extend(payload.get('results') or [])
        if len(rows) >= count:
            try:
                return normalize_bars(rows,interval,now,count=count,ticker=ticker), ('DELAYED' if 'DELAYED' in statuses else 'OK')
            except FeedError as exc:
                if exc.status != 422:
                    raise
        next_url = payload.get('next_url')
        if not next_url:
            break
        parsed = urlsplit(next_url)
        if parsed.scheme != 'https' or parsed.netloc != urlsplit(base).netloc or not parsed.path.startswith(f'/v2/aggs/ticker/{ticker}/range/'):
            raise FeedError('Polygon returned an invalid history page',502)
        url = base + parsed.path
        params = {k:v for k,v in parse_qsl(parsed.query) if k.lower() != 'apikey'}
    raise FeedError(f'Insufficient completed history for {ticker} {interval}m',422)


def close_available(timestamps: pd.Series, ticker: str, interval: int):
    """Completion timestamps, preserving stock-daily ET calendar semantics."""
    if interval == 1440 and not is_crypto(ticker):
        return (timestamps.dt.tz_convert(ET) + pd.DateOffset(days=1)).dt.tz_convert('UTC')
    return timestamps.dt.tz_convert('UTC') + pd.Timedelta(minutes=interval)


def realized_times(future: pd.Series, ticker: str, interval: int):
    times = close_available(pd.Series(future),ticker,interval)
    if not is_crypto(ticker) and interval == 60:
        start = pd.Timestamp(future.iloc[0]).date(); end = pd.Timestamp(future.iloc[-1]).date()
        schedule = CALENDAR.schedule(start_date=start,end_date=end)
        by_day = {day.date(): row.market_close for day,row in schedule.iterrows()}
        times = pd.Series([min(t,by_day[pd.Timestamp(stamp).tz_convert(ET).date()])
                           for t,stamp in zip(times,future)])
    return times


def scheduled_windows(df: pd.DataFrame, ticker: str, interval: int, slots):
    """Build inputs and realized paths exactly as available at scheduled times."""
    horizon = DEFAULT_PRED_LEN[interval]
    available = close_available(df.timestamps,ticker,interval)
    for decision in slots:
        # For stock final hourly bars, +60m is conservative; at all regular
        # scheduled times that final short bar is relevant only on the next day.
        indices = np.flatnonzero((available <= decision).to_numpy())
        if not len(indices) or indices[-1] < 399:
            continue
        idx = int(indices[-1]); hist = df.iloc[idx-399:idx+1].reset_index(drop=True)
        actual = df.iloc[idx+1:idx+1+horizon].reset_index(drop=True)
        if len(actual) != horizon:
            continue
        future = future_timestamps(hist.timestamps.iloc[-1],interval,horizon,ticker)
        if not pd.DatetimeIndex(future).equals(pd.DatetimeIndex(actual.timestamps)):
            continue
        when = realized_times(future,ticker,interval)
        if not (pd.DatetimeIndex(when) > decision).all():
            continue
        yield {'decision':decision, 'hist':hist, 'actual':actual, 'future':future, 'available':when}


def pause_for_live_slots():
    """Yield GPU during actual scheduled delivery to avoid a forecast timeout."""
    while True:
        now = pd.Timestamp.now(tz=ET)
        minute = now.hour*60 + now.minute
        if now.weekday() >= 5 or not any(-2 <= minute - (int(t[:2])*60+int(t[3:])) <= 5 for t in DEFAULT_TIMES):
            return
        print('Pausing research inference for the live forecast window',flush=True)
        time.sleep(30)


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sessions',type=int,default=36)
    parser.add_argument('--samples',type=int,default=5)
    parser.add_argument('--batch-origins',type=int,default=2)
    parser.add_argument('--output',default=str(ROOT/'outputs/reliability'/f"scheduled_walkforward_{pd.Timestamp.now(tz='UTC'):%Y%m%dT%H%M%SZ}.json"))
    parser.add_argument('--ticker',choices=('SPY','X:BTCUSD'),default=None)
    parser.add_argument('--interval',type=int,choices=(5,15,60,1440),default=None)
    parser.add_argument('--resume',action='store_true',help='Replace selected groups in an existing compatible report')
    args = parser.parse_args()
    if not 12 <= args.sessions <= 180 or not 2 <= args.samples <= 20 or args.batch_origins < 1:
        parser.error('sessions must be 12–180, samples 2–20, batch origins positive')
    path = Path(args.output); path.parent.mkdir(parents=True,exist_ok=True)
    slots = market_slots(pd.Timestamp.now(tz='UTC'),args.sessions)
    if len(slots) != args.sessions:
        parser.error('Insufficient past exchange sessions for requested evaluation')
    print(f'Selected {len(slots)} real exchange-session slots, one per day, balanced across 09:30/12:00/15:00 ET',flush=True)
    model,device = _load_predictor(ROOT/'models/Kronos-small',ROOT/'models/Kronos-Tokenizer-base')
    signature=artifact_signature(ROOT/'models/Kronos-small',ROOT/'models/Kronos-Tokenizer-base')
    if args.resume:
        report=json.loads(path.read_text(encoding='utf-8'))
        if report.get('method',{}).get('artifact_signature') != signature:
            raise SystemExit('Cannot resume with different model/tokenizer files')
        method=report.get('method',{})
        if method.get('sessions') != args.sessions or method.get('samples') != args.samples or method.get('temperatures') != list(TEMPERATURES):
            raise SystemExit('Cannot resume with different evaluation settings')
        selected_slots={s.isoformat() for s in slots}
        if any(r['decision'] not in selected_slots for group in report.get('results',[]) for r in group.get('records',[])):
            raise SystemExit('Cannot resume after the selected exchange sessions have changed')
    else:
        report = {'method':{'sessions':args.sessions,'actual_posting_times_et':list(DEFAULT_TIMES), 'origins_per_session':1,
                            'maturity_holdback_sessions':12,'lookback':400,'samples':args.samples,
                            'temperatures':list(TEMPERATURES),'top_p':0.9,'device':device,'artifact_signature':signature},'results':[]}
    # Long requested tests need enough prior bars as well as the reserved
    # maturity period; crypto trades continuously across weekends and holidays.
    span_days = max(1, int((pd.Timestamp.now(tz='UTC') - slots[0]).total_seconds() // 86400) + 8)
    trading_sessions = args.sessions + 12
    counts = {('SPY',5):max(5000,trading_sessions*78+424),
              ('SPY',15):max(2500,trading_sessions*26+424),
              ('SPY',60):max(1300,trading_sessions*7+418),
              ('SPY',1440):max(700,trading_sessions+420),
              ('X:BTCUSD',5):max(22000,span_days*288+424),
              ('X:BTCUSD',15):max(8000,span_days*96+424),
              ('X:BTCUSD',60):max(2500,span_days*24+418),
              ('X:BTCUSD',1440):max(900,span_days+410)}
    for interval in ((args.interval,) if args.interval else (5,15,60,1440)):
        for ticker in ((args.ticker,) if args.ticker else ('SPY','X:BTCUSD')):
            if args.resume:
                report['results']=[r for r in report['results'] if (r['ticker'],r['interval_minutes']) != (ticker,interval)]
            start=time.monotonic(); result={'ticker':ticker,'interval_minutes':interval,'horizon_bars':DEFAULT_PRED_LEN[interval], 'records':[]}
            try:
                df,status=load_history(ticker,interval,counts[(ticker,interval)])
                windows=list(scheduled_windows(df,ticker,interval,slots)); result['provider_status']=status
                print(f'{ticker} {interval}m: {len(windows)}/{len(slots)} scheduled origins; {len(df)} completed bars',flush=True)
                if not windows:
                    raise RuntimeError('No aligned and completed scheduled windows')
                report['results'].append(result)
                for first in range(0,len(windows),args.batch_origins):
                    pause_for_live_slots()
                    group=windows[first:first+args.batch_origins]
                    xs=[w['hist'].drop(columns='timestamps') for w in group for _ in range(args.samples)]
                    times=[w['hist'].timestamps for w in group for _ in range(args.samples)]
                    ys=[w['future'] for w in group for _ in range(args.samples)]
                    predictions={}
                    for j,temp in enumerate(TEMPERATURES):
                        torch.manual_seed(20261112 + interval*1000 + first*7 + j + (0 if ticker=='SPY' else 10000000))
                        predictions[str(temp)] = model.predict_batch(xs,times,ys,DEFAULT_PRED_LEN[interval],
                                                                     T=temp,top_p=.9,sample_count=1,verbose=False)
                    for k,w in enumerate(group):
                        entry={'decision':w['decision'].isoformat(),'asof':w['hist'].timestamps.iloc[-1].isoformat(),
                               'start':float(w['hist'].close.iloc[-1]),
                               'daily_volatility_30':daily_volatility(w['hist'].close) if ticker=='X:BTCUSD' and interval==1440 else None,
                               'actual':[float(x) for x in w['actual'].close],
                               'future':[pd.Timestamp(x).isoformat() for x in w['future']],
                               'available':[pd.Timestamp(x).isoformat() for x in w['available']], 'temperature_paths':{}}
                        for temp in TEMPERATURES:
                            paths=predictions[str(temp)][k*args.samples:(k+1)*args.samples]
                            values=np.stack([p['close'].to_numpy(dtype=float) for p in paths])
                            if values.shape != (args.samples,DEFAULT_PRED_LEN[interval]) or not np.isfinite(values).all() or (values<=0).any():
                                raise RuntimeError('Invalid forecast path output')
                            entry['temperature_paths'][str(temp)] = values.tolist()
                        result['records'].append(entry)
                    path.write_text(json.dumps(report,indent=2),encoding='utf-8')
                    if first % (args.batch_origins*5)==0:
                        print(f'  {ticker} {interval}m {len(result["records"])}/{len(windows)}',flush=True)
                result['seconds']=round(time.monotonic()-start,1)
                path.write_text(json.dumps(report,indent=2),encoding='utf-8')
                print(f'Completed {ticker} {interval}m in {result["seconds"]}s',flush=True)
            except Exception as exc:
                result['error']=f'{type(exc).__name__}: {exc}'
                if result not in report['results']:
                    report['results'].append(result)
                path.write_text(json.dumps(report,indent=2),encoding='utf-8')
                print(f'{ticker} {interval}m: {result["error"]}',flush=True)
    return 0 if all('error' not in x for x in report['results']) else 1


if __name__ == '__main__':
    raise SystemExit(run())
