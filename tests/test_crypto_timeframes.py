"""Market-calendar and aggregation regressions; fixtures are synthetic test data."""
import pandas as pd
import pytest
from webui import polygon_feed as live
from webui.watch_summary import summarize


def bars(times):
    return [dict(t=int(t.timestamp()*1000), o=100, h=102, l=99, c=101, v=10, vw=100.5) for t in times]


@pytest.mark.parametrize('interval', [1,5,15,60,240,1440])
def test_crypto_weekends_and_unfinished_bar(interval):
    step = pd.Timedelta(minutes=interval)
    times = pd.date_range('2026-10-03', periods=18, freq=step, tz='UTC')
    now = times[-1] + step/2
    df = live.normalize_bars(bars(times),interval,now,16,'X:BTCUSD')
    assert len(df) == 16 and df.timestamps.iloc[-1] == times[-2]
    assert str(df.timestamps.dt.tz) == 'UTC'
    future = live.future_timestamps(df.timestamps.iloc[-1],interval,30,'X:BTCUSD')
    assert future.iloc[0] == times[-1]
    assert (future.diff().dropna() == step).all()
    info = live.metadata(df,'X:BTCUSD',interval,now,'OK',now)
    assert info['market_open'] and info['timezone'] == 'UTC'


@pytest.mark.parametrize('interval,size',[ (60,7),(240,2)])
def test_stock_hourly_session_anchor_and_short_last_bar(interval,size):
    times = pd.date_range('2026-10-02T13:00Z','2026-10-02T20:00Z',freq='30min')
    df = live.normalize_bars(bars(times),interval,pd.Timestamp('2026-10-02T20:01Z'),size)
    assert df.timestamps.iloc[0] == pd.Timestamp('2026-10-02T09:30-04:00')
    assert len(df) == size and df.volume.sum() == 130
    assert df.amount.sum() == 13065
    future = live.future_timestamps(df.timestamps.iloc[-1],interval,3)
    assert future.iloc[0] == pd.Timestamp('2026-10-05T09:30-04:00')
    with pytest.raises(live.FeedError):
        live.normalize_bars(bars(times.delete(3)),interval,pd.Timestamp('2026-10-02T20:01Z'),size)


def test_hourly_early_close_and_dst():
    times=pd.date_range('2026-11-27T14:30Z','2026-11-27T17:30Z',freq='30min')
    df=live.normalize_bars(bars(times),240,pd.Timestamp('2026-11-27T18:01Z'),1)
    assert df.volume.iloc[0] == 70
    assert live.future_timestamps(df.timestamps.iloc[-1],240,1).iloc[0] == pd.Timestamp('2026-11-30T09:30-05:00')


def test_stock_daily_completion_and_future_dates():
    times=pd.date_range('2026-10-01',periods=2,freq='D',tz=live.TZ)
    df=live.normalize_bars(bars(times),1440,pd.Timestamp('2026-10-02T23:00-04:00'),1)
    assert df.timestamps.iloc[-1] == times[0]  # Today is still unfinished.
    future=live.future_timestamps(times[1],1440,3)
    assert list(future.dt.day) == [5,6,7]
    assert all(t.hour == 0 for t in future)
    assert live.provider_interval('SPY',1440) == (1,'day')
    assert live.provider_interval('SPY',240) == (30,'minute')
    assert live.provider_interval('X:ETHUSD',240) == (4,'hour')


def test_watch_does_not_publish_stock_close_for_crypto():
    result=summarize(None,'X:BTCUSD',60,pd.Timestamp('2026-10-05T16:00Z'))
    assert result['status'] == 'unavailable' and result['predicted_high'] is None
    assert 'Crypto' in result['reason']


def test_crypto_provider_route_and_history_range(monkeypatch):
    monkeypatch.setattr(live,'settings',lambda:('test-key','https://api.polygon.io'))
    now=pd.Timestamp.now(tz='UTC')
    times=pd.date_range(now.normalize()-pd.Timedelta(days=500),periods=500,freq='D')
    def get(url,**kwargs):
        assert '/ticker/X:BTCUSD/range/1/day/' in url
        assert str((now-pd.Timedelta(days=800)).date()) in url
        return type('Response',(),{'status_code':200,'json':lambda self:{'status':'OK','results':bars(times)}})()
    monkeypatch.setattr(live.requests,'get',get)
    df,info=live.PolygonFeed().candles('x:btcusd',1440,400)
    assert len(df) == 400 and info['market'] == 'crypto'
