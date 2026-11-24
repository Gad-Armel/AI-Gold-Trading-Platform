import unittest
from unittest.mock import patch
from services.research.gold_entry_coordination import assess_entry_coordination


@patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS', 0)
class EntryCoordinationTests(unittest.TestCase):
    def setUp(self):
        self.decision = dict(allowed=True, direction='BUY')
        self.peer = dict(direction='BUY', opened_epoch=100, entry_price=100, volume=.01)
        self.bars = [dict(time=300, open=101, close=102)]

    def assess(self, positions=None, bars=None, bid=102, ask=102.2):
        return assess_entry_coordination(self.decision, [self.peer] if positions is None else positions,
               self.bars if bars is None else bars, now=610, bid=bid, ask=ask)

    def test_first_setup_remains_eligible(self):
        self.assertTrue(self.assess(positions=[])['allowed'])

    def test_losing_or_spread_noise_position_cannot_duplicate_risk(self):
        self.assertFalse(self.assess(bid=99, ask=99.2)['allowed'])
        self.assertFalse(self.assess(bid=100.2, ask=100.4)['allowed'])

    def test_profitable_position_requires_new_completed_bar(self):
        self.assertFalse(self.assess(bars=[dict(time=0, open=100, close=101)])['allowed'])
        self.assertFalse(self.assess(bars=[dict(time=600, open=101, close=102)])['allowed'])

    def test_fresh_follow_through_can_add(self):
        self.assertTrue(self.assess()['allowed'])

    def test_opposing_candle_or_stale_data_cannot_confirm(self):
        self.assertFalse(self.assess(bars=[dict(time=300, open=103, close=102)])['allowed'])
        self.peer['opened_epoch'] = 1
        self.assertFalse(self.assess(bars=[dict(time=0, open=100, close=101)])['allowed'])

    def test_opposite_direction_is_independent(self):
        self.peer['direction'] = 'SELL'
        self.assertTrue(self.assess()['allowed'])

    def test_restart_does_not_erase_peer_entry_time(self):
        self.peer['opened_epoch'] = 400
        self.assertFalse(self.assess()['allowed'])

    def test_invalid_positions_fail_closed_for_additions(self):
        self.peer['opened_epoch'] = float('nan')
        self.assertFalse(self.assess()['allowed'])

    def test_sell_side_uses_ask_for_cushion(self):
        self.decision['direction'] = self.peer['direction'] = 'SELL'
        self.bars = [dict(time=300, open=100, close=99)]
        self.assertTrue(self.assess(bid=98, ask=98.2)['allowed'])

    def test_priority_preserves_scalp_access_while_existing_peer_loses(self):
        decision=dict(self.decision,horizon='SCALP')
        result=assess_entry_coordination(decision,[self.peer],[],now=610,bid=99,ask=99.2,scalp_priority=True)
        self.assertTrue(result['allowed'])
        self.assertEqual(result['stage'],'LEADING_SCALP')
        self.assertEqual(result['policy'],'STAGED_EXPOSURE_SCALP_PRIORITY_V1')
        # The decision itself is not granted execution authority by this gate.
        self.assertTrue(decision['allowed'])
        decision['allowed']=False
        assess_entry_coordination(decision,[self.peer],[],now=610,bid=99,ask=99.2,scalp_priority=True)
        self.assertFalse(decision['allowed'])

    def test_priority_still_stages_secondary_lanes_and_accepts_fresh_follow_through(self):
        for name in ('INTRADAY','SWING'):
            decision=dict(self.decision,horizon=name)
            losing=assess_entry_coordination(decision,[self.peer],self.bars,now=610,bid=99,ask=99.2,scalp_priority=True)
            confirmed=assess_entry_coordination(decision,[self.peer],self.bars,now=610,bid=102,ask=102.2,scalp_priority=True)
            self.assertFalse(losing['allowed'])
            self.assertTrue(confirmed['allowed'])


if __name__ == '__main__':
    unittest.main()
