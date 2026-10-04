import json
from types import SimpleNamespace
import pandas as pd
import pytest
from flask import Flask
from webui.watch_summary import summarize, remaining_session_times, register_watch_summary
from webui.polygon_feed import register_live_feed
from webui.access import configure_access
from webui import polygon_feed as live

NOW = pd.Timestamp('2026-10-02T16:06:00Z')


def forecast(now=NOW, interval=5):
    anchor = now.floor('5min') - pd.Timedelta(minutes=5)
    times = remaining_session_times(anchor,interval,now)
    row = lambda t:dict(timestamp=t.isoformat(),open=100,high=102,low=99,close=101)
    return dict(feed=dict(ticker='SPY',interval_minutes=interval,fetched_at=now.isoformat()),
                generated_at=now.isoformat(),forecast_anchor=anchor.isoformat(),
                candles=[row(anchor)],prediction_results=[row(t) for t in times])


def test_today_range_and_chart_never_contains_next_session():
    value=forecast()
    value['prediction_results'].append(dict(timestamp='2026-10-05T09:30:00-04:00',open=100,high=9999,low=1,close=500))
    summary=summarize(value,'SPY',5,NOW)
    assert summary['status']=='ready'
    assert summary['predicted_high']==102 and summary['predicted_low']==99
    assert summary['session_date']=='2026-10-02'
    assert all(pd.Timestamp(p['timestamp']).date()==NOW.date() for p in summary['predicted'])
    assert summary['predicted'][-1]['timestamp']=='2026-10-02T19:55:00+00:00'


def test_weekend_closed_has_no_old_or_next_day_numbers():
    result=summarize(forecast(),'SPY',5,pd.Timestamp('2026-10-04T15:00:00Z'))
    assert result['status']=='closed' and result['predicted_high'] is None and not result['predicted']


@pytest.mark.parametrize('value', [[], ['not a forecast'], {'feed': []}, {'feed': {'ticker':'SPY','interval_minutes':5},'forecast_anchor':None}])
def test_malformed_saved_payload_never_crashes(value):
    assert summarize(value,'SPY',5,NOW)['status'] in ('invalid','unavailable')


def test_partial_stale_invalid_missing_and_expiry():
    value=forecast();value['prediction_results']=value['prediction_results'][:5]
    assert summarize(value,'SPY',5,NOW)['status']=='partial'
    value=forecast();value['prediction_results'].pop(10)
    assert summarize(value,'SPY',5,NOW)['status']=='invalid'
    value=forecast();value['prediction_results'][-1]['high']=50
    result=summarize(value,'SPY',5,NOW)
    assert result['status']=='invalid' and result['quality_count']==1 and result['predicted_high'] is None
    assert summarize(forecast(),'SPY',5,NOW+pd.Timedelta(minutes=15))['status']=='stale'
    assert summarize(forecast(),'AAPL',5,NOW)['status']=='unavailable'


def test_early_close_and_dst():
    now=pd.Timestamp('2026-11-27T16:06:00Z')
    result=summarize(forecast(now),'SPY',5,now)
    assert result['market_close']=='2026-11-27T18:00:00+00:00'
    assert result['predicted'][-1]['timestamp']=='2026-11-27T17:55:00+00:00'


@pytest.mark.parametrize('now,last',[
    ('2026-10-04T15:00:00Z','2026-10-02T19:55:00Z'),
    ('2026-10-02T20:01:00Z','2026-10-02T19:55:00Z'),
    ('2026-10-02T13:20:00Z','2026-10-01T19:55:00Z'),
    ('2026-10-02T16:00:00Z','2026-10-02T14:00:00Z'),
])
def test_today_generation_rejects_closed_or_stale(now,last):
    with pytest.raises(ValueError):remaining_session_times(pd.Timestamp(last),5,pd.Timestamp(now))


def test_saved_route_read_only_and_invalid_selection(tmp_path,monkeypatch):
    app=Flask(__name__);register_watch_summary(app,tmp_path)
    (tmp_path/'SPY_5min_20261002.json').write_text(json.dumps(forecast()))
    monkeypatch.setattr(pd.Timestamp,'now',lambda **kwargs:NOW)
    client=app.test_client()
    assert client.get('/api/live/watch-summary').get_json()['status']=='ready'
    assert client.get('/api/live/watch-summary?ticker=../../x').status_code==400


def test_proxy_guard_requires_authenticated_session_and_matching_https_origin(monkeypatch):
    app=Flask(__name__)
    register_live_feed(app,SimpleNamespace(predictor=None,AVAILABLE_MODELS={}))
    configure_access(app,'a'*40)
    client=app.test_client()
    assert client.get('/api/live/watch-summary',base_url='https://kronos.example').status_code==401
    client.post('/login',base_url='https://kronos.example',data={'token':'a'*40})
    assert client.get('/api/live/watch-summary',base_url='https://kronos.example').status_code==200
    assert client.get('/api/live/watch-summary',base_url='http://kronos.example',headers={'Origin':'https://kronos.example'}).status_code==200
    assert client.post('/api/live/predict',base_url='https://kronos.example',headers={'Origin':'https://evil.example'},json={}).status_code==403


def test_today_prediction_endpoint_uses_close_horizon_and_refuses_weekend(tmp_path, monkeypatch):
    anchor=NOW.floor('5min')-pd.Timedelta(minutes=5)
    df=pd.DataFrame({'timestamps':pd.date_range(end=anchor,periods=400,freq='5min'),
                     'open':100.,'high':102.,'low':99.,'close':101.,'volume':10.,'amount':1000.})
    info={'ticker':'SPY','interval_minutes':5,'last_candle':anchor.isoformat(),'fetched_at':NOW.isoformat()}
    monkeypatch.setattr(live,'ROOT',tmp_path)
    monkeypatch.setattr(live.PolygonFeed,'candles',lambda *args:(df,info))
    monkeypatch.setattr(pd.Timestamp,'now',lambda **kwargs:NOW)
    calls=[]
    class Predictor:
        max_context=512
        def predict(self,**args):
            calls.append(args['pred_len'])
            assert args['y_timestamp'].iloc[-1]==pd.Timestamp('2026-10-02T19:55:00Z')
            return pd.DataFrame({'open':100.,'high':102.,'low':99.,'close':101.,'volume':10.,'amount':1000.},index=args['y_timestamp'])
    app=Flask(__name__);register_live_feed(app,SimpleNamespace(predictor=Predictor()))
    client=app.test_client()
    response=client.post('/api/live/predict',json={'target_today':True,'pred_len':30,'interval':5})
    assert response.status_code==200
    assert calls==[47]
    assert client.get('/api/live/watch-summary').get_json()['status']=='ready'
    monkeypatch.setattr(pd.Timestamp,'now',lambda **kwargs:pd.Timestamp('2026-10-04T15:00:00Z'))
    assert client.post('/api/live/predict',json={'target_today':True,'interval':5}).status_code==422
    assert calls==[47]
