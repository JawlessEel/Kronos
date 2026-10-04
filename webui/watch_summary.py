"""Read-only same-day Watch summaries; never starts inference or reads another session."""
import json
from pathlib import Path
import math
import pandas as pd
from flask import jsonify, request


def session_bounds(now):
    from webui.polygon_feed import CALENDAR, TZ
    now = pd.Timestamp(now).tz_convert('UTC')
    day = now.tz_convert(TZ).date()
    schedule = CALENDAR.schedule(day, day)
    if schedule.empty:
        return str(day), None, None
    row = schedule.iloc[0]
    return str(day), row.market_open, row.market_close


def remaining_session_times(last, interval, now):
    now = pd.Timestamp(now).tz_convert('UTC')
    last = pd.Timestamp(last).tz_convert('UTC')
    _, opening, closing = session_bounds(now)
    if opening is None or not opening <= now < closing:
        raise ValueError('Today is outside the regular trading session; no next-day Watch target is generated.')
    step = pd.Timedelta(minutes=interval)
    if last < opening or last + step > now or now - (last + step) > pd.Timedelta(minutes=30):
        raise ValueError('Latest completed candle is stale or not from today; refresh the feed before targeting close.')
    # Keep delayed-feed intervening predictions so the autoregressive timeline stays continuous.
    times = pd.Series(pd.date_range(last + step, closing - step, freq=step).tz_convert('America/New_York'))
    if times.empty or not (times >= now).any():
        raise ValueError('No full future candle remains before today closes.')
    return times


def summarize(result, ticker, interval, now):
    now = pd.Timestamp(now).tz_convert('UTC')
    day, opening, closing = session_bounds(now)
    output = dict(version=1, ticker=ticker, session_date=day, status='unavailable', reason='Generate a forecast through today close on the phone.',
                  market_close=closing.isoformat() if closing is not None else None, generated_at=None,
                  expires_at=None, predicted_high=None, predicted_low=None, high_time=None, low_time=None,
                  observed=[], predicted=[], quality_count=0, interval_minutes=interval)
    if opening is None or now >= closing or now < opening:
        output.update(status='closed', reason='No current-day regular-session target is available.')
        return output
    if not result:
        return output
    if not isinstance(result, dict) or not isinstance(result.get('feed', {}), dict):
        output.update(status='invalid', reason='Saved forecast is malformed; refresh on phone.')
        return output
    feed = result.get('feed', {})
    if feed.get('ticker') != ticker or feed.get('interval_minutes') != interval:
        return output
    try:
        anchor = pd.Timestamp(result['forecast_anchor']).tz_convert('UTC')
        generated = pd.Timestamp(result.get('generated_at') or feed['fetched_at']).tz_convert('UTC')
        step = pd.Timedelta(minutes=interval)
        expires = min(closing, generated + pd.Timedelta(minutes=15), anchor + step + pd.Timedelta(minutes=30))
        output.update(generated_at=generated.isoformat(), expires_at=expires.isoformat())
        if anchor < opening or anchor >= now or generated > now or now >= expires:
            output.update(status='stale', reason='Forecast expired or belongs to another session. Refresh on the phone.')
            return output
        def rows(key):
            return [(pd.Timestamp(row['timestamp']).tz_convert('UTC'),row) for row in result.get(key, [])]
        observed = [(t,r) for t,r in rows('candles') if opening <= t <= anchor]
        predicted = [(t,r) for t,r in rows('prediction_results') if now <= t and t+step <= closing]
        # A short-horizon forecast cannot advertise a through-close high/low.
        if not predicted or predicted[-1][0]+step != closing:
            output.update(status='partial', reason='Forecast does not reach today close. Generate a through-close forecast.')
            return output
        expected = pd.date_range(anchor+step, closing-step, freq=step)
        all_future = [(t,r) for t,r in rows('prediction_results') if anchor < t and t+step <= closing]
        if [t for t,_ in all_future] != list(expected):
            raise ValueError('Missing or unordered forecast bars')
        for _,r in observed+predicted:
            if not all(math.isfinite(float(r[k])) for k in ('open','high','low','close')):
                raise ValueError('Non-finite prices')
        bad = sum(r['high'] < max(r['open'],r['low'],r['close']) or r['low'] > min(r['open'],r['high'],r['close']) or min(r[k] for k in ('open','high','low','close')) <= 0 for _,r in predicted)
        output.update(observed=[dict(timestamp=t.isoformat(),close=r['close']) for t,r in observed],
                      predicted=[dict(timestamp=t.isoformat(),close=r['close']) for t,r in predicted], quality_count=bad)
        if bad:
            output.update(status='invalid', reason='Inconsistent predicted OHLC bounds; high/low withheld. Refresh on phone.')
            return output
        high=max(predicted,key=lambda pair:pair[1]['high']);low=min(predicted,key=lambda pair:pair[1]['low'])
        output.update(status='ready', reason='Predicted remaining-session range through today close; not the full-day realized high/low.',
                      predicted_high=high[1]['high'],predicted_low=low[1]['low'],high_time=high[0].isoformat(),low_time=low[0].isoformat())
        return output
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        output.update(status='invalid',reason='Saved forecast is malformed; refresh on phone.')
        return output


def register_watch_summary(app, directory):
    @app.get('/api/live/watch-summary')
    def watch_summary():
        from webui.polygon_feed import selection, FeedError
        try:
            ticker, interval = selection(request.args.get('ticker','SPY'),request.args.get('interval','5'))
        except FeedError as error:
            return jsonify(error=str(error)), error.status
        result = None
        files = sorted(Path(directory).glob(f'{ticker}_{interval}min_*.json'), reverse=True)
        for file in files[:10]:
            try:
                if file.stat().st_size > 10_000_000:
                    continue
                result = json.loads(file.read_text(encoding='utf-8'))
                break
            except (OSError, json.JSONDecodeError):
                continue
        response = jsonify(summarize(result,ticker,interval,pd.Timestamp.now(tz='UTC')))
        response.headers['Cache-Control']='no-store'
        return response
