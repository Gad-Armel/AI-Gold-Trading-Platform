import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from services.research.gold_exit_state import GoldExitStateStore
from services.research.gold_adaptive_exit import evaluate_adaptive_exit


class ExitRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'state.json'
        self.account=SimpleNamespace(login=7,server='Demo',trade_mode=0)
        self.positions=[dict(ticket=42,direction='BUY',entry_price=100.,volume=.01)]
        self.context=dict(available=True,atr=2.,momentum=1.,trend=1.,close=110.,previous_low=90.,previous_high=120.)
        self.state={}
        self.evaluate(1000,110.)

    def evaluate(self,now,bid):
        return evaluate_adaptive_exit(dict(allowed=True,direction='BUY'),self.positions,self.context,
            self.state,now=now,bid=bid,ask=bid+.2,feed_age=0.,config={},risk_usd=4.,contract_size=100.)

    def save(self):
        GoldExitStateStore(self.path,self.account).save({'SCALP':dict(exit_state=self.state,
            previous_tickets=[42],last_closed_bar=None)},1001)

    def test_peak_survives_restart_and_triggers_giveback(self):
        self.save();store=GoldExitStateStore(self.path,self.account)
        self.state=store.load(1002)['SCALP']['exit_state']
        self.assertEqual(store.status,'RESTORED');self.context['momentum']=-1.
        self.assertTrue(self.evaluate(1003,106.)['close'])

    def test_fast_entry_period_survives_restart(self):
        store = GoldExitStateStore(self.path, self.account)
        for period in (1, 5, 15, 30):
            store.save({'SCALP': dict(exit_state={}, previous_tickets=[], last_closed_bar=None,
                                     entry_period_seconds=period)}, 1001)
            self.assertEqual(store.load(1002)['SCALP']['entry_period_seconds'], period)
        data = json.loads(self.path.read_text())
        data['lanes']['SCALP']['entry_period_seconds'] = True
        self.path.write_text(json.dumps(data))
        self.assertEqual(store.load(1002), {})

    def test_three_position_profit_peaks_survive_restart(self):
        self.state['position_signature'] = [[t, 'BUY', 100., .01] for t in (42, 43, 44)]
        self.state['ticket_profit_peaks'] = {'42': 6., '43': 2., '44': 10.}
        self.save()
        loaded = GoldExitStateStore(self.path, self.account).load(1002)
        self.assertEqual(loaded['SCALP']['exit_state']['ticket_profit_peaks'],
                         {'42': 6., '43': 2., '44': 10.})

    def test_other_account_and_new_position_cannot_inherit_peak(self):
        self.save()
        other=SimpleNamespace(login=8,server='Demo',trade_mode=0)
        self.assertEqual(GoldExitStateStore(self.path,other).load(1002),{})
        self.state=GoldExitStateStore(self.path,self.account).load(1002)['SCALP']['exit_state']
        self.positions[0]['ticket']=43;self.context['momentum']=-1.
        self.assertFalse(self.evaluate(1003,101.)['close'])

    def test_downtime_does_not_complete_confirmation(self):
        self.state['adverse_since']=1000
        self.state['conscience_state']=dict(signature=['a'],collapsed_since=1000)
        self.save()
        loaded=GoldExitStateStore(self.path,self.account).load(2000)['SCALP']['exit_state']
        self.assertIsNone(loaded['adverse_since'])
        self.assertNotIn('conscience_state',loaded)

    def test_corrupt_future_and_nonfinite_state_rejected(self):
        self.path.write_text('{bad')
        self.assertEqual(GoldExitStateStore(self.path,self.account).load(1002),{})
        self.save()
        self.assertEqual(GoldExitStateStore(self.path,self.account).load(900),{})
        data=json.loads(self.path.read_text());data['lanes']['SCALP']['exit_state']['peak_move']=float('nan')
        self.path.write_text(json.dumps(data))
        self.assertEqual(GoldExitStateStore(self.path,self.account).load(1002),{})

    def test_adverse_excursion_and_flat_reentry_marker_survive(self):
        self.evaluate(1001,98.)
        self.assertEqual(self.state['trough_move'],-2.)
        self.save();loaded=GoldExitStateStore(self.path,self.account).load(1002)
        self.assertEqual(loaded['SCALP']['exit_state']['trough_move'],-2.)
        GoldExitStateStore(self.path,self.account).save({'SCALP':dict(exit_state={},previous_tickets=[],
            last_closed_bar='2026-01-01T10:00:00Z')},1002)
        self.assertEqual(GoldExitStateStore(self.path,self.account).load(1003)['SCALP']['last_closed_bar'],
            '2026-01-01T10:00:00Z')

    def test_post_exit_pause_and_candle_wait_survive_restart(self):
        from services.research.gold_continuous_session import post_exit_blocks
        lane = dict(exit_state={}, previous_tickets=[], last_closed_bar=None,
                    last_exit_at=990, last_exit_direction='SELL',
                    candle_confirmation_state=dict(direction='BUY', peak=100, waiting_since=980))
        store = GoldExitStateStore(self.path, self.account)
        store.save({'SCALP': lane}, 1000)
        loaded = store.load(1005)
        self.assertTrue(post_exit_blocks(loaded, now=1005))
        self.assertFalse(post_exit_blocks(loaded, now=1020))
        self.assertEqual(loaded['SCALP']['candle_confirmation_state']['waiting_since'], 980)

    def test_future_cooldown_is_rejected(self):
        self.save()
        data = json.loads(self.path.read_text())
        data['lanes']['SCALP']['last_exit_at'] = 2000
        self.path.write_text(json.dumps(data))
        self.assertEqual(GoldExitStateStore(self.path,self.account).load(1002), {})


if __name__=='__main__':unittest.main()
