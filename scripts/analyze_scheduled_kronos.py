#!/usr/bin/env python3
"""Causal replay of scheduled Kronos forecasts, residual bands and shrinkage."""
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


def analyze(records, temperature, horizon):
    history=[]; rows=[]
    for item in sorted(records,key=lambda r:r['decision']):
        start=float(item['start']); actual=float(item['actual'][-1])
        paths=np.asarray(item['temperature_paths'][str(float(temperature))],dtype=float)
        mean=float(paths[:,-1].mean()); raw_low,raw_high=np.quantile(paths[:,-1],[.1,.9])
        fit=calibrate_forecast(history,item['decision'],temperature,horizon)
        fixed=calibrate_forecast(history,item['decision'],temperature,horizon,fixed_weight=.25)
        row={'decision':item['decision'],'start':start,'actual':actual,'raw':mean,
             'raw_low':float(raw_low),'raw_high':float(raw_high),'ready':bool(fit['ready'])}
        if fit['ready']:
            weight=fit['weight']; center=start+weight*(mean-start); radius=start*fit['offsets'][-1]
            fixed_center=start+.25*(mean-start); fixed_radius=start*fixed['offsets'][-1]
            all_actual=np.asarray(item['actual'],dtype=float)
            means=paths.mean(axis=0)
            raw_lows,raw_highs=np.quantile(paths,[.1,.9],axis=0)
            dynamic_centers=start+weight*(means-start)
            dynamic_radii=start*np.asarray(fit['offsets'])
            fixed_centers=start+.25*(means-start)
            fixed_radii=start*np.asarray(fixed['offsets'])
            row.update({'steps':len(all_actual),
                        'raw_path_coverage':int(np.sum((raw_lows<=all_actual)&(all_actual<=raw_highs))),
                        'residual_path_coverage':int(np.sum((dynamic_centers-dynamic_radii<=all_actual)&(all_actual<=dynamic_centers+dynamic_radii))),
                        'fixed25_path_coverage':int(np.sum((fixed_centers-fixed_radii<=all_actual)&(all_actual<=fixed_centers+fixed_radii))),
                        'fixed25_sample_path_coverage':int(np.sum((start+.25*(raw_lows-start)<=all_actual)&(all_actual<=start+.25*(raw_highs-start)))),'fixed25':fixed_center,'fixed25_lower':max(0.0,fixed_center-fixed_radius),
                        'fixed25_upper':fixed_center+fixed_radius,
                        'adjusted':center,'lower':max(0.0,center-radius),'upper':center+radius,
                        'weight':weight,'calibration_count':fit['endpoint_count'],
                        'calibration_through':fit['through']})
        rows.append(row);history.append(item)
    evaluable=[r for r in rows if r['ready']]
    if not evaluable:
        return {'all_windows':len(rows),'evaluated':0,'rows':rows}
    def mae(key):
        return float(np.mean([abs(r[key]-r['actual'])/r['start']*100 for r in evaluable]))
    return {'all_windows':len(rows),'evaluated':len(evaluable),
            'mean_model_mae_pct':mae('raw'), 'adjusted_mae_pct':mae('adjusted'), 'fixed25_mae_pct':mae('fixed25'),
            'no_change_mae_pct':mae('start'),
            'raw_sample_spread_coverage':sum(r['raw_low']<=r['actual']<=r['raw_high'] for r in evaluable),
            'residual_band_coverage':sum(r['lower']<=r['actual']<=r['upper'] for r in evaluable),
            'fixed25_band_coverage':sum(r['fixed25_lower']<=r['actual']<=r['fixed25_upper'] for r in evaluable),
            'fixed25_sample_band_coverage':sum(r['start']+.25*(r['raw_low']-r['start'])<=r['actual']<=r['start']+.25*(r['raw_high']-r['start']) for r in evaluable),
            'path_points':sum(r['steps'] for r in evaluable),
            'raw_path_coverage':sum(r['raw_path_coverage'] for r in evaluable),
            'residual_path_coverage':sum(r['residual_path_coverage'] for r in evaluable),
            'fixed25_path_coverage':sum(r['fixed25_path_coverage'] for r in evaluable),
            'fixed25_sample_path_coverage':sum(r['fixed25_sample_path_coverage'] for r in evaluable),
            'mean_band_width_pct':float(np.mean([(r['upper']-r['lower'])/r['start']*100 for r in evaluable])),
            'fixed25_band_width_pct':float(np.mean([(r['fixed25_upper']-r['fixed25_lower'])/r['start']*100 for r in evaluable])),
            'weight_counts':{str(w):sum(r['weight']==w for r in evaluable) for w in (0.0,.25,.5,.75,1.0)},
            'rows':rows}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('input',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    data=json.loads(args.input.read_text(encoding='utf-8'))
    result={'method':{'minimum_unique_realized_forecasts':12,'target_residual_quantile':.8,
                      'candidate_weights':[0,.25,.5,.75,1], 'minimum_past_improvement_over_no_change':.05,
                      'max_history':60,'max_age_days':180,
                      'warning':'Empirical intervals only; dependent, overlapping financial data do not guarantee coverage.'},
            'results':[]}
    for group in data['results']:
        if 'error' in group:
            result['results'].append({'ticker':group['ticker'],'interval_minutes':group['interval_minutes'],'error':group['error']})
            continue
        item={'ticker':group['ticker'],'interval_minutes':group['interval_minutes'],
              'horizon_bars':group['horizon_bars'],'temperatures':{}}
        for temp in (1.0,.9,.8):
            item['temperatures'][str(temp)]=analyze(group['records'],temp,group['horizon_bars'])
        result['results'].append(item)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    for group in result['results']:
        if 'temperatures' not in group:
            print(group);continue
        print(group['ticker'],group['interval_minutes'],[(temp, {k:v for k,v in summary.items() if k!='rows'}) for temp,summary in group['temperatures'].items()])
    return 0


if __name__=='__main__':
    raise SystemExit(main())
