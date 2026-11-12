import json
import tempfile
import unittest
from pathlib import Path
import pandas as pd
from webui.calibration_store import append_forecast, artifact_signature, future_availability, load_calibration, save_calibration, update_actuals


class CalibrationStoreTests(unittest.TestCase):
    def test_weight_or_tokenizer_change_produces_new_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            model=Path(tmp)/"model"; tokenizer=Path(tmp)/"tokenizer"
            model.mkdir(); tokenizer.mkdir()
            for folder in (model,tokenizer):
                (folder/"config.json").write_text("{}")
                (folder/"model.safetensors").write_bytes(b"weights")
            first=artifact_signature(model,tokenizer)
            self.assertEqual(first,artifact_signature(model,tokenizer))
            (tokenizer/"model.safetensors").write_bytes(b"changed")
            self.assertNotEqual(first,artifact_signature(model,tokenizer))

    def test_roundtrip_and_corrupt_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json'
            state=load_calibration(path)
            state['series']['SPY|5']=[{'decision':'test'}]
            save_calibration(path,state)
            self.assertEqual(load_calibration(path),state)
            path.write_text('{bad')
            with self.assertRaises(RuntimeError):
                load_calibration(path)

    def test_only_completed_timestamp_matches_fill_outcomes(self):
        bars=pd.DataFrame({'timestamps':pd.to_datetime(['2026-11-12T15:05:00Z']), 'close':[101.0]})
        rec={'future':['2026-11-12T10:05:00-05:00','2026-11-12T15:10:00Z'], 'actual':[None,None]}
        self.assertEqual(update_actuals([rec],bars),1)
        self.assertEqual(rec['actual'],[101.0,None])

    def test_short_stock_session_and_daily_availability(self):
        future=pd.Series(pd.to_datetime(["2026-11-27T12:30:00-05:00"]))
        self.assertEqual(pd.Timestamp(future_availability(future,"SPY",60)[0]),pd.Timestamp("2026-11-27T13:00:00-05:00"))
        day=pd.Series(pd.to_datetime(["2026-11-27T00:00:00-05:00"]))
        self.assertEqual(pd.Timestamp(future_availability(day,"SPY",1440)[0]),pd.Timestamp("2026-11-28T00:00:00-05:00"))

    def test_append_dedup_and_bounded(self):
        rows=[]
        for i in range(3): append_forecast(rows,{'decision':str(i)},limit=2)
        append_forecast(rows,{'decision':'2','new':True},limit=2)
        self.assertEqual([r['decision'] for r in rows],['1','2'])
        self.assertTrue(rows[-1]['new'])

class SeedTests(unittest.TestCase):
    def test_seed_rejects_future_outcomes_and_preserves_existing(self):
        from scripts.seed_kronos_calibration import merge_matured
        from webui.calibration_store import series_key
        now=pd.Timestamp('2026-11-12T18:00:00Z')
        rows=[]
        for i in range(12):
            rows.append({'decision':f'2026-10-{i+1:02d}T15:00:00Z', 'actual':[100],
                         'available':['2026-11-01T00:00:00Z']})
        future={'decision':'2026-11-12T17:00:00Z','actual':[999],
                'available':['2026-11-13T00:00:00Z']}
        report={'method':{'samples':5,'lookback':400},'results':[{'ticker':'SPY','interval_minutes':5,'records':rows+[future]}]}
        key=series_key('SPY',5,400,5,'Kronos-small')
        state={'version':1,'series':{key:[{'decision':rows[0]['decision'],'original':True}]}}
        self.assertEqual(merge_matured(report,state,now),11)
        self.assertTrue(state['series'][key][0]['original'])
        self.assertEqual(len(state['series'][key]),12)


if __name__=='__main__': unittest.main()
