"""Point-in-time alignment and actual exchange-session posting slots."""
import unittest
import numpy as np
import pandas as pd
from scripts.scheduled_kronos_walkforward import market_slots, realized_times, scheduled_windows
from webui.calibration_store import future_availability
from webui.polygon_feed import CALENDAR


class ScheduledWindowsTests(unittest.TestCase):
    def test_rotating_slots_exclude_holidays_and_early_close(self):
        slots=market_slots(pd.Timestamp('2026-12-02T20:00:00Z'),50,maturity_sessions=1)
        local=[s.tz_convert('America/New_York') for s in slots]
        self.assertFalse(any(t.strftime('%Y-%m-%d')=='2026-11-26' for t in local))
        early=[t for t in local if t.strftime('%Y-%m-%d')=='2026-11-27']
        self.assertEqual(len(early),1)
        self.assertLess(early[0].hour,13)
        self.assertTrue(all(t.strftime('%H:%M') in {'09:30','12:00','15:00'} for t in local))
        self.assertTrue(any(t.strftime('%H:%M')=='15:00' for t in local))

    def test_crypto_uses_only_bars_completed_by_decision(self):
        bars=pd.DataFrame({'timestamps':pd.date_range('2026-10-31',periods=1300,freq='5min',tz='UTC'),
                           'close':np.arange(1300)+100.0})
        decision=pd.Timestamp('2026-11-02T14:30:00Z')
        w=list(scheduled_windows(bars,'X:BTCUSD',5,[decision]))
        self.assertEqual(len(w),1)
        self.assertEqual(w[0]['hist'].timestamps.iloc[-1],pd.Timestamp('2026-11-02T14:25:00Z'))
        self.assertEqual(w[0]['actual'].timestamps.iloc[0],decision)
        self.assertEqual(w[0]['available'].iloc[0],decision+pd.Timedelta(minutes=5))
        self.assertEqual(len(w[0]['hist']),400)

    def test_replay_and_live_agree_on_outcome_availability(self):
        future=pd.Series(pd.to_datetime(["2026-11-27T12:30:00-05:00"]))
        replay=realized_times(future,"SPY",60)
        live=future_availability(future,"SPY",60)
        self.assertEqual(pd.Timestamp(replay.iloc[0]),pd.Timestamp(live[0]))
        self.assertEqual(pd.Timestamp(live[0]),pd.Timestamp("2026-11-27T13:00:00-05:00"))

    def test_stock_regular_session_open_uses_prior_day(self):
        schedule=CALENDAR.schedule(start_date='2026-10-12',end_date='2026-11-04')
        stamps=[]
        for row in schedule.itertuples():
            stamps.extend(pd.date_range(row.market_open,row.market_close-pd.Timedelta(minutes=5),freq='5min'))
        bars=pd.DataFrame({'timestamps':pd.DatetimeIndex(stamps).tz_convert('America/New_York'),
                           'close':np.arange(len(stamps))+100.0})
        decision=pd.Timestamp('2026-11-02T14:30:00Z')
        w=list(scheduled_windows(bars,'SPY',5,[decision]))
        self.assertEqual(len(w),1)
        self.assertEqual(w[0]['hist'].timestamps.iloc[-1].strftime('%Y-%m-%d %H:%M'),'2026-10-30 15:55')
        self.assertEqual(w[0]['actual'].timestamps.iloc[0],decision)


if __name__ == '__main__':
    unittest.main()
