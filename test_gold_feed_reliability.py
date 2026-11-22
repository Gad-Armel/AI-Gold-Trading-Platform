import unittest
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from config import gold_consensus_settings as settings
from services.research.gold_advisory_v3 import build_gold_advisory_v3,_tick_frame,_window
from services.research.gold_tick_history import TickHistoryBuffer
from services.research.gold_runtime_health import market_health,isolated_advisor
from services.research.gold_fast_protection import quote_protection
from services.research.gold_adaptive_exit import market_exit_context
from services.research.gold_advisory_consensus import build_gold_advisory_consensus
from test_gold_advisory_v3 import FakeTickMT5


class FeedReliabilityTests(unittest.TestCase):
    def setUp(self):
        setting=patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS',0)
        setting.start();self.addCleanup(setting.stop)

    def test_empty_missing_malformed_ticks_do_not_crash(self):
        for rows in (None,[],42,[{'bid':2000,'ask':2001}],[{'time':0,'bid':float('inf'),'ask':float('inf')}]):
            with self.subTest(rows=rows):
                mt5=FakeTickMT5();mt5.rows=rows
                report=build_gold_advisory_v3(mt5)
                self.assertFalse(report['available'])
                self.assertEqual(report['overall'],'WAIT')
                self.assertTrue(all(not h['source_usable'] for h in report['horizons'].values()))
                self.assertEqual(_window(_tick_frame(rows),15,100)['ticks'],0)

    def test_stale_history_cannot_become_fresh_when_report_is_regenerated(self):
        report=build_gold_advisory_v3(FakeTickMT5(stale=True))
        self.assertFalse(report['available'])
        consensus=build_gold_advisory_consensus(report,report,report)
        self.assertFalse(consensus['horizons']['SCALP']['advisors']['MT5_TICK_FLOW']['source_usable'])

    def test_per_horizon_quality_survives_consensus_adapter(self):
        report=build_gold_advisory_v3(FakeTickMT5())
        report['horizons']['SCALP']['source_usable']=False
        consensus=build_gold_advisory_consensus(report,report,report)
        self.assertFalse(consensus['horizons']['SCALP']['advisors']['MT5_TICK_FLOW']['source_usable'])

    def test_advisor_exception_is_unavailable_and_recovery_clears_error(self):
        errors={}
        def fail():raise KeyError('timestamp')
        self.assertFalse(isolated_advisor('ticks',fail,errors)['available'])
        self.assertIn('KeyError',errors['ticks'])
        self.assertTrue(isolated_advisor('ticks',lambda:dict(available=True),errors)['available'])
        self.assertEqual(errors,{})

    def test_connected_terminal_does_not_mean_fresh_quote(self):
        snapshot=SimpleNamespace(tick_time_msc=100_000,bid=2000.,ask=2000.2)
        health=market_health(snapshot,SimpleNamespace(connected=True),now=1000)
        self.assertFalse(health['available'])
        self.assertEqual(health['quote_age_seconds'],900)
        self.assertIn('900.0s',health['reason'])
        self.assertFalse(market_health(snapshot,None,now=100)['available'])
        self.assertFalse(market_health(snapshot,SimpleNamespace(connected=True),now=90)['available'])
        self.assertTrue(market_health(snapshot,SimpleNamespace(connected=True),now=101)['available'])

    def test_frozen_snapshot_cannot_keep_old_candles_current(self):
        bars=pd.DataFrame(dict(time=pd.date_range('2026-09-15T12:00:00Z',periods=60,freq='min'),
            open=2000.,high=2001.,low=1999.,close=2000.))
        snap=SimpleNamespace(candles={'M1':bars},timestamp=pd.Timestamp('2026-09-15T13:00:00Z'))
        self.assertTrue(market_exit_context(snap,'SCALP')['available'])
        self.assertFalse(market_exit_context(snap,'SCALP',now_utc=pd.Timestamp('2026-09-15T13:20:00Z'))['available'])

    def test_quote_profit_protection_works_without_an_advisor(self):
        positions=[dict(ticket=1,direction='BUY',entry_price=2000.,volume=.01)]
        result=quote_protection(positions,{},horizon='SCALP',now=100,quote_time=100,
            bid=2001,ask=2001.1,flow=dict(available=True,reversal_risk=.9))
        self.assertTrue(result['close'])
        self.assertIn('Flow reversal',result['reason'])
        stale=quote_protection(positions,{},horizon='SCALP',now=120,quote_time=100,
            bid=2001,ask=2001.1,flow=dict(available=True,reversal_risk=.9))
        self.assertFalse(stale['close'])

    def test_paper_quote_expires_during_processing_and_shutdown(self):
        import tempfile
        from services.execution.gold_paper_portfolio import GoldPaperPortfolio
        with tempfile.TemporaryDirectory() as folder:
            paper=GoldPaperPortfolio(root=folder)
            paper.mark(2000,2000.1,100,0)
            paper.positions=[dict(ticket=1,horizon='SCALP',entry_price=1999.,direction='BUY',volume=.01,sl=1998.)]
            expired=100+float(settings.EXIT_MAX_FEED_AGE_SECONDS)+1
            result=paper.close_lane('SCALP','test shutdown',now=expired)
            self.assertEqual(result['closed_count'],0)
            self.assertEqual(len(paper.positions),1)
            self.assertFalse(paper.valid_quote)
            self.assertFalse(paper.valid_exit_quote)
            paper.mark(2000,2000.1,expired+1,0)
            result=paper.close_lane('SCALP','new quote',now=expired+1.5)
            self.assertEqual(result['closed_count'],1)
            self.assertEqual(paper.trades[0]['closed_epoch'],expired+1.5)


class IncrementalHistoryTests(unittest.TestCase):
    def setUp(self):
        setting=patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS',0)
        setting.start();self.addCleanup(setting.stop)
        # This fixture returns its requested endpoints. Keep that test about
        # incremental history/deduplication; dedicated clock tests cover jitter.
        jitter=patch('config.gold_consensus_settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS',0)
        jitter.start();self.addCleanup(jitter.stop)
        self.now=datetime(2026,9,15,12,tzinfo=timezone.utc)
        self.buffer=TickHistoryBuffer()
        self.calls=[]
        self.failure=False
        parent=self
        class MT5:
            COPY_TICKS_ALL=-1
            def copy_ticks_range(self,symbol,start,end,flags):
                parent.calls.append((start,end))
                if parent.failure:return None
                return [dict(time_msc=int(t.timestamp()*1000),bid=2000.,ask=2000.2)
                        for t in (start,end)]
            def last_error(self):return (-1,'test history failure')
        self.mt5=MT5()

    def test_fetches_incrementally_and_deduplicates(self):
        first,health=self.buffer.refresh(self.mt5,'XAUUSD',self.now)
        self.assertTrue(health['available'])
        self.assertEqual(health['request_seconds'],920)
        second,health=self.buffer.refresh(self.mt5,'XAUUSD',self.now+timedelta(seconds=5))
        self.assertEqual(health['request_seconds'],6)
        self.buffer.refresh(self.mt5,'XAUUSD',self.now+timedelta(seconds=5))
        self.assertFalse(self.buffer.frame.duplicated(['timestamp','bid','ask']).any())

    def test_cache_does_not_hide_provider_failure_and_recovers(self):
        self.buffer.refresh(self.mt5,'XAUUSD',self.now)
        self.failure=True
        frame,health=self.buffer.refresh(self.mt5,'XAUUSD',self.now+timedelta(seconds=1))
        self.assertFalse(health['available'])
        self.assertGreater(len(frame),0)
        self.failure=False
        self.assertTrue(self.buffer.refresh(self.mt5,'XAUUSD',self.now+timedelta(seconds=2))[1]['available'])

    def test_expired_cache_cannot_be_reused(self):
        self.buffer.refresh(self.mt5,'XAUUSD',self.now)
        self.failure=True
        frame,health=self.buffer.refresh(self.mt5,'XAUUSD',self.now+timedelta(seconds=1000))
        self.assertTrue(frame.empty)
        self.assertFalse(health['available'])
