"""Calibration may use only unique, completed past forecast outcomes."""
import unittest
import pandas as pd
from webui.forecast_calibration import adjust_forecast, calibrate_forecast, matured_records


def record(day, *, asof=None, end_lag=2, predicted=110.0, actual=110.0):
    decision=pd.Timestamp('2026-01-01T00:00:00Z')+pd.Timedelta(days=day)
    return {'decision':decision.isoformat(),'asof':(asof or decision).isoformat(), 'start':100.0,
            'available':[(decision+pd.Timedelta(days=i+1)).isoformat() for i in range(end_lag)],
            'actual':[actual]*end_lag,
            'temperature_paths':{'1.0':[[predicted]*end_lag for _ in range(5)]}}


class CalibrationTests(unittest.TestCase):
    def test_future_outcomes_never_change_result(self):
        past=[record(i) for i in range(20)]
        now=pd.Timestamp('2026-01-25T00:00:00Z')
        before=calibrate_forecast(past,now,1.0,2)
        not_matured=record(24,predicted=500,actual=1)
        after=calibrate_forecast(past+[not_matured],now,1.0,2)
        self.assertEqual(before,after)
        self.assertTrue(before['ready'])
        self.assertEqual(before['weight'],1.0)
        self.assertEqual(before['offsets'],[0.0,0.0])

    def test_duplicate_asof_is_counted_once(self):
        now=pd.Timestamp('2026-03-01T00:00:00Z')
        first=record(1)
        duplicate=record(2,asof=pd.Timestamp(first['asof']))
        self.assertEqual(len(matured_records([first,duplicate],now,1.0,1)),1)

    def test_unreliable_model_shrinks_to_no_change(self):
        now=pd.Timestamp('2026-03-01T00:00:00Z')
        result=calibrate_forecast([record(i,predicted=120,actual=99) for i in range(20)],now,1.0,2)
        self.assertTrue(result['ready'])
        self.assertEqual(result['weight'],0.0)
        self.assertAlmostEqual(result['offsets'][1],0.01)

    def test_fixed_blend_uses_past_residuals_and_reports_weight(self):
        now=pd.Timestamp('2026-03-01T00:00:00Z')
        result=calibrate_forecast([record(i,predicted=120,actual=99) for i in range(20)],now,1.0,2,fixed_weight=.25)
        self.assertTrue(result['ready'])
        self.assertEqual(result['weight'],.25)
        self.assertAlmostEqual(result['offsets'][1],.06)
        with self.assertRaises(ValueError):
            calibrate_forecast([],now,1.0,2,fixed_weight=1.1)

    def test_insufficient_history_never_claims_calibration(self):
        result=calibrate_forecast([record(1)],pd.Timestamp('2026-03-01T00:00:00Z'),1.0,2)
        self.assertFalse(result['ready'])
        self.assertEqual(result['offsets'],[])
        self.assertEqual(result['weight'],1.0)

    def test_adjusted_candles_and_empirical_intervals(self):
        import numpy as np
        frame=pd.DataFrame({"open":[104.],"high":[108.],"low":[102.],"close":[106.]})
        fit={"ready":True,"weight":.25,"offsets":[.1]}
        result,low,high,weight,method=adjust_forecast(frame,np.array([95]),np.array([110]),100,fit)
        self.assertEqual((result.iloc[0]["open"],result.iloc[0]["high"],result.iloc[0]["low"],result.iloc[0]["close"]),(101,102,100.5,101.5))
        self.assertEqual((low[0],high[0],weight,method),(91.5,111.5,.25,"empirical"))
        raw,low,high,weight,method=adjust_forecast(frame,np.array([95]),np.array([110]),100,{"ready":False})
        self.assertEqual((raw.iloc[0]["close"],low[0],high[0],weight,method),(106,95,110,1.0,"sample"))

    def test_timezone_required(self):
        with self.assertRaises(ValueError):
            calibrate_forecast([],pd.Timestamp('2026-03-01'),1.0,2)


class AnalyzerTests(unittest.TestCase):
    def test_replay_waits_for_matured_outcomes_and_scores_both_path_and_endpoint(self):
        from scripts.analyze_scheduled_kronos import analyze
        rows=[record(i,predicted=120,actual=99) for i in range(20)]
        result=analyze(rows,1.0,2)
        self.assertGreater(result["evaluated"],0)
        self.assertLess(result["evaluated"],20)
        self.assertEqual(result["path_points"],2*result["evaluated"])
        self.assertEqual(result["fixed25_band_coverage"],result["evaluated"])
        self.assertEqual(result["fixed25_path_coverage"],result["path_points"])
        self.assertGreater(result["fixed25_mae_pct"],result["no_change_mae_pct"])



if __name__ == '__main__':
    unittest.main()
