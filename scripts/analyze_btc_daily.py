#!/usr/bin/env python3
"""Compare BTC daily models and empirical bands using a chronological holdout.

Point settings and interval method are chosen on the earlier partition only.
All historical calibration outcomes must have matured by each decision time.
Financial time series are dependent; observed coverage is not a guarantee.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from webui.forecast_calibration import calibrate_forecast  # noqa: E402
from webui.btc_daily_research import volatility_scaled_calibration  # noqa: E402

TEMPS=(1.0,.9,.8)
WEIGHTS=(0.0,.25,.5,.75,1.0)


def replay(records,temp,weight):
    history=[]; rows=[]
    for index,rec in enumerate(sorted(records,key=lambda x:x['decision'])):
        horizon=len(rec['actual']); start=float(rec['start']); actual=float(rec['actual'][-1])
        paths=np.asarray(rec['temperature_paths'][str(float(temp))],dtype=float)
        center=start+weight*(float(paths[:,-1].mean())-start)
        absolute=calibrate_forecast(history,rec['decision'],temp,horizon,fixed_weight=weight)
        scaled=volatility_scaled_calibration(history,rec['decision'],temp,horizon,
                                             float(rec['daily_volatility_30']),weight=weight)
        row={'index':index,'decision':rec['decision'],'asof':rec['asof'],'available_end':rec['available'][-1],
             'start':start,'actual':actual,'forecast':center,'ready':bool(absolute['ready'] and scaled['ready'])}
        if row['ready']:
            absolute_radius=start*absolute['offsets'][-1]; scaled_radius=start*scaled['offsets'][-1]
            row.update({'absolute_lower':max(0.,center-absolute_radius),'absolute_upper':center+absolute_radius,
                        'scaled_lower':max(0.,center-scaled_radius),'scaled_upper':center+scaled_radius,
                        'calibration_count':absolute['endpoint_count']})
        rows.append(row); history.append(rec)
    return rows


def metrics(rows):
    rows=[r for r in rows if r['ready']]
    if not rows:
        return {'count':0}
    error=lambda r:abs(r['forecast']-r['actual'])/r['start']*100
    return {'count':len(rows), 'mae_pct':float(np.mean([error(r) for r in rows])),
            'direction_correct':sum(int(np.sign(r['forecast']-r['start'])==np.sign(r['actual']-r['start'])) for r in rows),
            'absolute_covered':sum(int(r['absolute_lower']<=r['actual']<=r['absolute_upper']) for r in rows),
            'scaled_covered':sum(int(r['scaled_lower']<=r['actual']<=r['scaled_upper']) for r in rows),
            'absolute_width_pct':float(np.mean([(r['absolute_upper']-r['absolute_lower'])/r['start']*100 for r in rows])),
            'scaled_width_pct':float(np.mean([(r['scaled_upper']-r['scaled_lower'])/r['start']*100 for r in rows]))}


def nonoverlapping(rows):
    """Greedy diagnostic subset whose prior horizon has fully matured."""
    result=[]; available=None
    for row in rows:
        if not row['ready']:
            continue
        when=pd.Timestamp(row['decision'])
        if available is None or when>=available:
            result.append(row)
            available=pd.Timestamp(row['available_end'])
    return result


def analyze(records,holdout=40):
    if len(records)<holdout+40:
        raise ValueError('Insufficient origins for warmup, selection and holdout')
    split=len(records)-holdout; results={}
    for temp in TEMPS:
        for weight in WEIGHTS:
            rows=replay(records,temp,weight)
            results[f'{temp}:{weight}']={'training':metrics(rows[:split]),'holdout':metrics(rows[split:]),
                                       'holdout_nonoverlap':metrics(nonoverlapping(rows[split:])), 'rows':rows}
    candidates=[(v['training']['mae_pct'], t, w) for t in TEMPS for w in WEIGHTS
                for v in [results[f'{t}:{w}']] if v['training']['count']>=30]
    if not candidates:
        raise ValueError('Insufficient matured training outcomes')
    _,temp,weight=min(candidates,key=lambda item:(item[0],item[2],abs(item[1]-1.0)))
    chosen=results[f'{temp}:{weight}']; train=chosen['training']; test=chosen['holdout']
    method='scaled' if (train['scaled_covered']/train['count']>=.8 and
                        train['scaled_width_pct']<train['absolute_width_pct']) else 'absolute'
    baseline=results['1.0:0.25']['holdout']; nochange=results['1.0:0.0']['holdout']
    narrower=(test[f'{method}_width_pct'] < baseline['absolute_width_pct'])
    point_ok=(test['count']>=30 and test['mae_pct']<baseline['mae_pct'] and test['mae_pct']<=nochange['mae_pct'])
    band_ok=(test['count']>=30 and test[f'{method}_covered']/test['count']>=.8 and narrower)
    current=results['1.0:0.25']; ct=current['training']; ch=current['holdout']
    current_band_ok=(ct['count']>=30 and ct['scaled_covered']/ct['count']>=.8
                     and ct['scaled_width_pct']<ct['absolute_width_pct']
                     and ch['count']>=30 and ch['scaled_covered']/ch['count']>=.8
                     and ch['scaled_width_pct']<ch['absolute_width_pct'])
    return {'method':{'holdout':holdout,'split_index':split,'candidates':{'temperatures':list(TEMPS),'model_weights':list(WEIGHTS)},
                      'training_rule':'minimum point MAE; volatility band only when training coverage >=80% and narrower',
                      'deployment_rule':'holdout >=80% coverage, narrower than current, lower MAE than current and no worse than no-change',
                      'warning':'Overlapping windows and changing market regimes limit statistical confidence; nonoverlap subsets are diagnostic and small.'},
            'selected':{'temperature':temp,'weight':weight,'interval_method':method,
                        'holdout_point_improved':point_ok,'holdout_band_passed':band_ok,
                        'holdout_passes_accuracy_and_coverage':bool(point_ok and band_ok),
                        'holdout_band_narrower_than_current':narrower},
            'current_setting_scaled_band_passed':current_band_ok,'candidates':results}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('input',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--holdout',type=int,default=40)
    args=parser.parse_args();data=json.loads(args.input.read_text(encoding='utf-8'))
    groups=[x for x in data['results'] if x.get('ticker')=='X:BTCUSD' and x.get('interval_minutes')==1440 and not x.get('error')]
    if len(groups)!=1:
        raise SystemExit('Expected one successful BTC daily series')
    result=analyze(groups[0]['records'],args.holdout)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('Selected from earlier windows:',result['selected'])
    for temp in TEMPS:
        for weight in (0.,.25,.5,1.):
            print('temperature',temp,'weight',weight,'holdout',result['candidates'][f'{temp}:{weight}']['holdout'])


if __name__=='__main__':main()
