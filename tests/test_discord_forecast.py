"""Forecast candles and model-sample uncertainty shown in Discord charts."""
import unittest
import numpy as np
import pandas as pd

from scripts.run_discord_forecast import aggregate_forecast_paths, _plot_panel
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
