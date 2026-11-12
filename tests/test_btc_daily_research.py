import unittest
import numpy as np
import pandas as pd
from webui.btc_daily_research import daily_volatility,volatility_scaled_calibration


def row(day,*,sigma=.02,pred=110,actual=105,delay=2):
    d=pd.Timestamp('2026-01-01T00:00:00Z')+pd.Timedelta(days=day)
    return {'decision':d.isoformat(),'asof':d.isoformat(),'start':100.,'daily_volatility_30':sigma,
            'available':[(d+pd.Timedelta(days=j+1)).isoformat() for j in range(delay)],
            'actual':[actual]*delay,'temperature_paths':{'0.9':[[pred]*delay for _ in range(5)]}}


class BTCVolatilityTests(unittest.TestCase):
    def test_scale_requires_causal_finite_history(self):
        closes=100*np.exp(np.sin(np.arange(31))*.03)
        self.assertGreater(daily_volatility(closes),0)
        with self.assertRaises(ValueError): daily_volatility(closes[:30])
        closes[-1]=float('nan')
        with self.assertRaises(ValueError): daily_volatility(closes)

    def test_future_outcomes_excluded_and_scale_adapts(self):
        history=[row(i) for i in range(20)]
        now=pd.Timestamp('2026-01-25T00:00:00Z')
        low=volatility_scaled_calibration(history,now,.9,2,.01)
        high=volatility_scaled_calibration(history+[row(24,actual=1)],now,.9,2,.04)
        self.assertTrue(low['ready'])
        self.assertEqual(low['counts'],high['counts'])
        self.assertAlmostEqual(high['offsets'][-1],4*low['offsets'][-1])

    def test_missing_volatility_stays_in_warmup(self):
        history=[row(i) for i in range(20)]
        for r in history: del r['daily_volatility_30']
        result=volatility_scaled_calibration(history,pd.Timestamp('2026-03-01T00:00:00Z'),.9,2,.02)
        self.assertFalse(result['ready'])
        self.assertEqual(result['offsets'],[])

class HoldoutSelectionTests(unittest.TestCase):
    def test_selection_uses_training_partition_not_later_actuals(self):
        from unittest.mock import patch
        from scripts.analyze_btc_daily import analyze
        def fake_replay(records,temp,weight):
            rows=[]
            for i,rec in enumerate(records):
                actual=rec['actual']
                err=0.0 if (temp,weight)==(.8,.25) else 1.0
                decision=pd.Timestamp('2026-01-01T00:00:00Z')+pd.Timedelta(days=i)
                rows.append({'index':i,'decision':decision.isoformat(),'available_end':(decision+pd.Timedelta(days=10)).isoformat(),
                             'start':100.,'actual':actual,'forecast':actual+err,
                             'ready':True,'absolute_lower':actual-5,'absolute_upper':actual+5,
                             'scaled_lower':actual-2,'scaled_upper':actual+2})
            return rows
        records=[{'actual':101.} for _ in range(80)]
        with patch('scripts.analyze_btc_daily.replay',side_effect=fake_replay):
            first=analyze(records,40)['selected']
            for r in records[-40:]: r['actual']=140.
            second=analyze(records,40)['selected']
        self.assertEqual((first['temperature'],first['weight']),(.8,.25))
        self.assertEqual((second['temperature'],second['weight']),(.8,.25))


if __name__=="__main__": unittest.main()
