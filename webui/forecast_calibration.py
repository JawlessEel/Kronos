"""Causal, empirical forecast blending and rolling residual sample bands.

Only previously issued forecasts and outcomes available before the current
origin may be used. Financial time series are dependent and shift over time;
these empirical intervals do not carry a guaranteed coverage probability.
"""
from __future__ import annotations

import math
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)


def _utc(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        raise ValueError('Calibration timestamps must include a timezone')
    return stamp.tz_convert('UTC')


def matured_records(records: list[dict[str, Any]], now: Any, temp: float,
                    step: int, *, max_age_days: int = 180, limit: int = 60):
    """Unique input histories with the specified outcome known by `now`."""
    now = _utc(now); oldest = now - pd.Timedelta(days=max_age_days)
    key = str(float(temp)); unique = {}
    for record in records:
        try:
            decision = _utc(record['decision'])
            available = _utc(record['available'][step])
            observed_asof = _utc(record['asof'])
            actual = float(record['actual'][step])
            start = float(record['start'])
            values = np.asarray(record['temperature_paths'][key],dtype=float)
            if not (oldest <= decision < now and observed_asof <= decision < available <= now and math.isfinite(actual)
                    and actual > 0 and math.isfinite(start) and start > 0
                    and values.ndim == 2 and values.shape[0] >= 2 and values.shape[1] > step
                    and np.isfinite(values[:, step]).all() and (values[:,step] > 0).all()):
                continue
            # Multiple posts can use the same last daily/hourly bar; retain one
            # mature origin per as-of timestamp to avoid counting it repeatedly.
            asof = observed_asof.isoformat()
            prev = unique.get(asof)
            candidate = (decision, start, float(values[:,step].mean()), actual, available)
            if prev is None or decision > prev[0]:
                unique[asof] = candidate
        except (KeyError, IndexError, TypeError, ValueError, OverflowError):
            continue
    return sorted(unique.values(),key=lambda row: row[0])[-limit:]


def calibrate_forecast(records: list[dict[str, Any]], now: Any, temp: float,
                       horizon: int, *, min_history: int = 12, coverage: float = 0.8,
                       fixed_weight: float | None = None):
    """Fit a conservative blend and empirical per-step errors using past data.

    Returns ``ready=False`` until enough distinct, fully realized histories
    exist. Residual quantiles are descriptive under dependence and shift, not
    guaranteed coverage. Candidate weights shrink the model toward no change.
    """
    if horizon < 1 or min_history < 2 or not 0 < coverage < 1 or (fixed_weight is not None and not 0 <= fixed_weight <= 1):
        raise ValueError('Invalid calibration configuration')
    prior = matured_records(records,now,temp,horizon-1)
    if len(prior) < min_history:
        return {'ready':False,'weight':1.0,'counts':[], 'offsets':[], 'endpoint_count':len(prior)}
    losses = {}
    for weight in WEIGHTS:
        losses[weight] = float(np.mean([abs((actual-start) - weight*(pred-start))/start
                                        for _,start,pred,actual,_ in prior]))
    if fixed_weight is None:
        weight = min(WEIGHTS,key=lambda w: losses[w])
        # Only move away from the baseline when past error improves by at least 5%.
        if losses[weight] > losses[0.0]*0.95:
            weight = 0.0
    else:
        weight = fixed_weight
        if weight not in losses:
            losses[weight] = float(np.mean([abs((actual-start) - weight*(pred-start))/start
                                            for _,start,pred,actual,_ in prior]))
    offsets=[]; counts=[]
    for step in range(horizon):
        earlier = matured_records(records,now,temp,step)
        counts.append(len(earlier))
        if len(earlier) < min_history:
            return {'ready':False,'weight':1.0,'counts':counts,'offsets':[], 'endpoint_count':len(prior)}
        residuals=sorted(abs((actual-start)-weight*(pred-start))/start for _,start,pred,actual,_ in earlier)
        rank=min(len(residuals),math.ceil((len(residuals)+1)*coverage))
        offsets.append(float(residuals[rank-1]))
    return {'ready':True,'weight':weight,'counts':counts,'offsets':offsets,
            'endpoint_count':len(prior),'through':max(row[4] for row in prior).isoformat(),
            'past_mae':losses[weight], 'past_baseline_mae':losses[0.0]}


def adjust_forecast(center: pd.DataFrame, sample_low: np.ndarray, sample_high: np.ndarray,
                    start: float, fit: dict[str, Any]):
    """Apply a validated blend and pointwise historical residual ranges.

    If calibration is not ready, retain the raw mean and sample spread. The
    historical ranges are empirical, not guaranteed prediction coverage.
    """
    result=center.copy()
    if not fit.get('ready'):
        return result,np.asarray(sample_low),np.asarray(sample_high),1.0,'sample'
    weight=float(fit['weight']); offsets=np.asarray(fit['offsets'],dtype=float)
    if not 0 <= weight <= 1 or offsets.shape != (len(result),) or not np.isfinite(offsets).all() or (offsets<0).any():
        raise ValueError('Invalid calibrated forecast parameters')
    for column in ('open','high','low','close'):
        result[column]=start+weight*(result[column]-start)
    close=result['close'].to_numpy(dtype=float)
    return result,np.maximum(0,close-start*offsets),close+start*offsets,weight,'empirical'
