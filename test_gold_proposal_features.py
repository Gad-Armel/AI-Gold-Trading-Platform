import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import pandas as pd

from services.research.gold_adaptive_exit import market_exit_context
from services.research.gold_research_recorder import GoldResearchRecorder


class ProposalFeatureTests(unittest.TestCase):
    def snapshot(self):
        frame=pd.DataFrame(dict(time=pd.date_range('2026-01-01',periods=60,freq='1min',tz='UTC'),
            open=100.,high=102.,low=99.,close=101.))
        return SimpleNamespace(candles={'M1':frame},timestamp=pd.Timestamp('2026-01-01T01:00:00Z'),
            tick_time_msc=1,bid=101.,ask=101.2,quote_age_seconds=0.)

    def test_gap_uses_only_completed_candles_and_is_research_only(self):
        snap=self.snapshot();frame=snap.candles['M1']
        frame.loc[59,['open','high','low','close']]=[104,106,103,105]
        context=market_exit_context(snap,'SCALP')
        self.assertGreater(context['structure_research']['bullish_gap_atr'],0)
        self.assertEqual(context['structure_research']['role'],'RESEARCH_ONLY')
        snap.timestamp=pd.Timestamp('2026-01-01T00:59:30Z')
        self.assertEqual(market_exit_context(snap,'SCALP')['structure_research']['bullish_gap_atr'],0)

    def test_sweep_requires_reclaim_of_previous_range(self):
        snap=self.snapshot();frame=snap.candles['M1']
        frame.loc[59,['open','high','low','close']]=[100,102,98,100]
        self.assertTrue(market_exit_context(snap,'SCALP')['structure_research']['downside_sweep'])
        frame.loc[59,'close']=98.5
        self.assertFalse(market_exit_context(snap,'SCALP')['structure_research']['downside_sweep'])

    def test_new_release_is_recorded_within_same_bar_without_timestamp_spam(self):
        snap=self.snapshot()
        lane=dict(adaptive_market={'bar_id':'same-bar'},decision={'allowed':False},entry_timing_ready=False,
                  positions=[],adaptive_exit={})
        news={'generated_at':'one','relevant_events':[]}
        with tempfile.TemporaryDirectory() as folder:
            recorder=GoldResearchRecorder(folder)
            recorder.record(snap,{'SCALP':lane},news)
            news['generated_at']='two';recorder.record(snap,{'SCALP':lane},news)
            news['relevant_events']=[dict(event_time='2026-01-01T05:00:00Z',actual=1,forecast=2)]
            recorder.record(snap,{'SCALP':lane},news)
            news['relevant_events'][0]['actual']=3
            recorder.record(snap,{'SCALP':lane},news)
            rows=[json.loads(line) for p in Path(folder).glob('decisions*') for line in p.read_text().splitlines()]
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[-1]['news']['relevant_events'][0]['actual'],3)

    def test_position_and_exit_change_is_recorded_before_next_bar(self):
        snap=self.snapshot()
        lane=dict(adaptive_market={'bar_id':'same'},decision={},entry_timing_ready=False,positions=[],adaptive_exit={})
        with tempfile.TemporaryDirectory() as folder:
            recorder=GoldResearchRecorder(folder);recorder.record(snap,{'SCALP':lane},{})
            lane['positions']=[{'ticket':7}];lane['adaptive_exit']={'reason':'Thesis weakened'}
            recorder.record(snap,{'SCALP':lane},{})
            rows=[json.loads(line) for p in Path(folder).glob('decisions*') for line in p.read_text().splitlines()]
        self.assertEqual(len(rows),2);self.assertEqual(rows[-1]['positions'],[{'ticket':7}])


if __name__=='__main__':unittest.main()
