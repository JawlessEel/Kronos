"""Causal realized-volatility scale for experimental BTC daily intervals."""
from __future__ import annotations
import numpy as np


def daily_volatility(closes, lookback=30):
    """Standard deviation of the last `lookback` daily log returns."""
    values=np.asarray(closes,dtype=float)
    if lookback<2 or len(values)<lookback+1:
        raise ValueError('Insufficient historical closes for volatility scale')
    tail=values[-(lookback+1):]
    if not np.isfinite(tail).all() or (tail<=0).any():
        raise ValueError('Volatility inputs must be finite positive closes')
    return max(float(np.std(np.diff(np.log(tail)),ddof=1)),1e-4)


def volatility_scaled_calibration(records, now, temp, horizon, current_volatility, *,
                                  weight=.25, min_history=12, coverage=.8, max_age_days=180, limit=60):
    """Causal per-step empirical errors scaled by prior 30-day volatility.

    It is a historical heuristic for nonstationary data, not a coverage
    guarantee. Missing scales are ignored and lead to explicit warmup.
    """
    import math
    import pandas as pd
    from webui.forecast_calibration import _utc
    now=_utc(now)
    if (horizon<1 or min_history<2 or not 0<coverage<1 or not 0<=weight<=1
            or not math.isfinite(current_volatility) or current_volatility<=0):
        raise ValueError('Invalid volatility-calibration settings')
    offsets=[]; counts=[]; latest=[]
    for step in range(horizon):
        unique={}
        for r in records:
            try:
                decision=_utc(r['decision']); asof=_utc(r['asof']); available=_utc(r['available'][step])
                start=float(r['start']); actual=float(r['actual'][step]); sigma=float(r['daily_volatility_30'])
                paths=np.asarray(r['temperature_paths'][str(float(temp))],dtype=float)
                if not (now-pd.Timedelta(days=max_age_days)<=decision<now and asof<=decision<available<=now
                        and math.isfinite(start) and start>0 and math.isfinite(actual) and actual>0
                        and math.isfinite(sigma) and sigma>0 and paths.ndim==2 and paths.shape[0]>=2
                        and paths.shape[1]>step and np.isfinite(paths[:,step]).all() and (paths[:,step]>0).all()):
                    continue
                pred=float(paths[:,step].mean())
                scaled_error=abs((actual-start)-weight*(pred-start))/start/sigma
                key=asof.isoformat(); previous=unique.get(key)
                if previous is None or decision>previous[0]:
                    unique[key]=(decision,scaled_error,available)
            except (KeyError,IndexError,TypeError,ValueError,OverflowError):
                continue
        prior=sorted(unique.values(),key=lambda x:x[0])[-limit:]
        counts.append(len(prior))
        if len(prior)<min_history:
            return {'ready':False,'counts':counts,'offsets':[],'endpoint_count':counts[-1]}
        ordered=sorted(x[1] for x in prior)
        rank=min(len(ordered),math.ceil((len(ordered)+1)*coverage))
        offsets.append(float(ordered[rank-1]*current_volatility))
        latest.append(max(x[2] for x in prior))
    return {'ready':True,'weight':weight,'counts':counts,'offsets':offsets,
            'endpoint_count':counts[-1],'through':latest[-1].isoformat()}
