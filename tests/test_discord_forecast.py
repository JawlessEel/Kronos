"""Forecast candles and model-sample uncertainty shown in Discord charts."""
import unittest
import numpy as np
import pandas as pd

from scripts.run_discord_forecast import aggregate_forecast_paths, generate_ticker_forecast, _plot_panel
from scripts.benchmark_discord_forecasts import origins, score


class ForecastPathsTests(unittest.TestCase):
    def path(self, close, high=99, low=101):
        return pd.DataFrame({"open": [100.0], "high": [high], "low": [low],
                             "close": [close], "volume": [1.0], "amount": [100.0]},
                            index=pd.date_range("2026-11-12", periods=1, tz="UTC"))

    def test_bounds_include_open_and_close_and_spread_uses_independent_closes(self):
        paths = [self.path(x) for x in (96.0, 98.0, 100.0, 102.0, 104.0)]
        result, low, high = aggregate_forecast_paths(paths)
        self.assertEqual(result.iloc[0]["open"], 100.0)
        self.assertEqual(result.iloc[0]["close"], 100.0)
        self.assertEqual(result.iloc[0]["high"], 101.0)
        self.assertEqual(result.iloc[0]["low"], 99.0)
        self.assertAlmostEqual(low[0], np.quantile([96,98,100,102,104], .1))
        self.assertAlmostEqual(high[0], np.quantile([96,98,100,102,104], .9))
        self.assertEqual(paths[0].iloc[0]["high"], 99.0)

    def test_bounds_fix_open_close_beyond_high_low(self):
        result, _, _ = aggregate_forecast_paths([self.path(104), self.path(106)])
        self.assertEqual(result.iloc[0]["high"], 105)
        self.assertEqual(result.iloc[0]["low"], 99)

    def test_plot_shows_spread_and_keeps_actual_time_label_readable(self):
        import matplotlib.pyplot as plt
        hist = pd.DataFrame({"timestamps": pd.date_range("2026-11-12", periods=100, freq="5min", tz="UTC"),
                             "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0})
        future = pd.date_range(hist.timestamps.iloc[-1] + pd.Timedelta(minutes=5), periods=24, freq="5min")
        pred = pd.DataFrame({"open":100.0,"high":102.0,"low":99.0,"close":101.0}, index=future)
        fig, ax = plt.subplots()
        try:
            summary = _plot_panel(ax, hist, pred, "SPY", 5, np.full(24, 98), np.full(24, 104), 5)
            self.assertEqual((summary["close_sample_p10"], summary["close_sample_p90"], summary["sample_count"]), (98, 104, 5))
            self.assertIn("sample spread", ax.get_legend().get_texts()[0].get_text())
            ticks = ax.get_xticks()
            self.assertGreaterEqual(min(np.diff(ticks)), 10)
            self.assertEqual(ax.get_xlabel(), "Time (ET)")
            labeled = {line.get_label(): line.get_color() for line in ax.lines}
            self.assertEqual(next(v for k,v in labeled.items() if k.startswith("63 EMA")), "#ec4899")
            self.assertEqual(next(v for k,v in labeled.items() if k.startswith("200 EMA")), "#ff9800")
            self.assertEqual(ax.lines[-2].get_color(), "#ec4899")
            self.assertEqual(ax.lines[-1].get_color(), "#ff9800")
        finally:
            plt.close(fig)

    def test_nonfinite_and_inconsistent_paths_fail_closed(self):
        with self.assertRaises(ValueError):
            aggregate_forecast_paths([self.path(float("nan")), self.path(100)])
        with self.assertRaises(ValueError):
            aggregate_forecast_paths([self.path(100), self.path(100).rename(index=lambda x: x + pd.Timedelta(days=1))])
        with self.assertRaises(ValueError):
            aggregate_forecast_paths([self.path(100)])


class ForecastIntegrationTests(unittest.TestCase):
    def test_calibrated_forecast_uses_only_past_and_records_raw_paths(self):
        import tempfile
        from pathlib import Path
        from webui.calibration_store import series_key
        now=pd.Timestamp.now(tz="UTC").floor("5min")
        bars=pd.DataFrame({"timestamps":pd.date_range(end=now-pd.Timedelta(minutes=5),periods=400,freq="5min"),
                           "open":100.,"high":102.,"low":99.,"close":100.,"volume":1.,"amount":100.})
        class Feed:
            def candles(self,ticker,interval,count): return bars.copy(),{"provider_status":"OK"}
        class Predictor:
            def predict_batch(self,**kw):
                return [pd.DataFrame({"open":109.,"high":108.,"low":111.,"close":110.,"volume":1.,"amount":100.},index=kw["y_timestamp_list"][0]) for _ in range(5)]
        history=[]
        for i in range(20):
            decision=now-pd.Timedelta(days=25-i)
            history.append({"decision":decision.isoformat(),"asof":decision.isoformat(),"start":100.,
                            "future":[],"available":[(decision+pd.Timedelta(minutes=5*(j+1))).isoformat() for j in range(24)],
                            "actual":[99.]*24,"temperature_paths":{"1.0":[[110.]*24 for _ in range(5)]}})
        key=series_key("X:BTCUSD",5,400,5,"Kronos-small")
        state={"version":1,"series":{key:history}}
        with tempfile.TemporaryDirectory() as tmp:
            result=generate_ticker_forecast(Feed(),Predictor(),"X:BTCUSD",[5],Path(tmp),400,"test",sample_count=5,temperature=1.0,model_weight=.25,calibration_state=state)
            tf=result["timeframes"][0]
            self.assertTrue(Path(result["chart_path"]).is_file())
            self.assertEqual(tf["uncertainty_method"],"empirical")
            self.assertEqual(tf["model_weight"],.25)
            self.assertEqual(tf["pred_end_close"],102.5)
            self.assertLess(tf["forecast_band_lower"],tf["pred_end_close"])
            self.assertGreater(tf["forecast_band_upper"],tf["pred_end_close"])
            self.assertEqual(len(history),21)
            self.assertEqual(history[-1]["temperature_paths"]["1.0"][0][-1],110.0)
            self.assertIsNone(history[-1]["actual"][-1])
            self.assertEqual(tf['forecast_bars'],24)
            self.assertEqual(len(tf['forecast_path']),24)
            self.assertEqual(tf['forecast_path'][-1]['close'],tf['pred_end_close'])
            self.assertEqual(tf['forecast_end_at'],tf['forecast_path'][-1]['timestamp'])
            self.assertEqual(tf['forecast_available_at'],tf['forecast_path'][-1]['available_at'])
            self.assertEqual(pd.Timestamp(tf['reference_available_at']),now)
            self.assertEqual(tf['data_session'],'crypto_24_7')
            self.assertEqual(len(tf['configuration_fingerprint']),64)
            self.assertTrue(all(pd.Timestamp(row['available_at']) > pd.Timestamp(row['timestamp']) for row in tf['forecast_path']))

    def test_equity_all_session_isolates_calibration_and_keeps_immutable_chart(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from webui.calibration_store import series_key
        now=pd.Timestamp('2026-11-12T15:00:00Z')
        bars=pd.DataFrame({'timestamps':pd.date_range(end=now-pd.Timedelta(minutes=5),periods=400,freq='5min'),
                           'open':100.,'high':102.,'low':99.,'close':100.,'volume':1.,'amount':100.})
        calls=[]
        class Feed:
            def candles(self,ticker,interval,count,*,equity_session):
                calls.append(equity_session)
                return bars.copy(),{'provider_status':'DELAYED','data_session':'equity_all',
                                    'session':'All available provider stock sessions', 'observed_hours':['04','09','16','19']}
        class Predictor:
            def predict_batch(self,**kw):
                return [pd.DataFrame({'open':100.,'high':102.,'low':99.,'close':101.,'volume':1.,'amount':100.},index=kw['y_timestamp_list'][0]) for _ in range(5)]
        old_key=series_key('SPY',5,400,5,'Kronos-small',signature='weights')
        state={'version':1,'series':{old_key:[{'decision':'old'}]}}
        with tempfile.TemporaryDirectory() as tmp, patch('scripts.run_discord_forecast.pd.Timestamp.now',return_value=now):
            first=generate_ticker_forecast(Feed(),Predictor(),'SPY',[5],Path(tmp),400,'test',calibration_state=state,model_signature='weights')
            before=Path(first['chart_path']).read_bytes()
            second=generate_ticker_forecast(Feed(),Predictor(),'SPY',[5],Path(tmp),400,'test',calibration_state=state,model_signature='weights')
            tf=first['timeframes'][0]
            self.assertEqual(calls,['all','all'])
            self.assertEqual(state['series'][old_key],[{'decision':'old'}])
            self.assertEqual(len(state['series']),2)
            self.assertEqual(tf['uncertainty_method'],'sample')
            self.assertEqual(tf['provider_status'],'DELAYED')
            self.assertEqual(tf['model_fingerprint'],'weights')
            self.assertEqual(tf['data_session'],'equity_all')
            self.assertEqual(tf['observed_hours'],['04','09','16','19'])
            self.assertNotEqual(first['chart_path'],second['chart_path'])
            self.assertEqual(Path(first['chart_path']).read_bytes(),before)



class WalkForwardTests(unittest.TestCase):
    def test_origins_are_prior_only_spread_and_nonoverlapping(self):
        bars = pd.DataFrame({"timestamps":pd.date_range("2026-01-01", periods=1000, freq="5min", tz="UTC"),
                             "close": np.arange(1000) + 100.0})
        windows = list(origins(bars, "X:BTCUSD", 5, 24, 6))
        self.assertEqual(len(windows), 6)
        for hist, actual, future in windows:
            self.assertEqual(len(hist), 400)
            self.assertEqual(len(actual), 24)
            self.assertLess(hist.timestamps.iloc[-1], actual.timestamps.iloc[0])
            self.assertTrue(pd.DatetimeIndex(actual.timestamps).equals(pd.DatetimeIndex(future)))
        for (_, previous, _), (_, following, _) in zip(windows, windows[1:]):
            self.assertLess(previous.timestamps.iloc[-1], following.timestamps.iloc[0])

    def test_error_score_uses_last_close_baseline(self):
        rows = [{"start":100, "actual":110, "forecast":105},
                {"start":100, "actual":90, "forecast":95}]
        result = score(rows, "forecast")
        self.assertEqual(result["mae_pct"], 5.0)
        self.assertEqual(result["baseline_mae_pct"], 10.0)
        self.assertEqual(result["direction_correct"], 2)
        self.assertEqual(result["beat_no_change"], 2)


if __name__ == "__main__":
    unittest.main()
