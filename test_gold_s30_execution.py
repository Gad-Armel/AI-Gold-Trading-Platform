import unittest
import json
from unittest.mock import patch

from services.research.gold_s30_execution import entry_check, load_costs


class S30ExecutionTests(unittest.TestCase):
    @patch('config.gold_consensus_settings.FAST_RANGE_COST_FILTER_ENABLED', False)
    @patch('services.research.gold_s30_execution.load_costs', return_value=dict(commission_price=2., slippage_price=2.))
    def test_range_cost_failure_is_warning_not_entry_veto(self, mocked):
        blocks, report = entry_check(dict(direction='BUY'), self.ticks(), now=335,
            plan=dict(required_bars=3, after_epoch=None), cost_path='unused')
        self.assertEqual(blocks, [])
        self.assertFalse(report['fast_candidate']['cost_screen_passed'])
        self.assertFalse(report['fast_candidate']['range_cost_screen_enforced'])
        self.assertTrue(any('estimated round-trip cost' in warning for warning in report['fast_candidate']['warnings']))

    @patch('services.research.gold_s30_execution.load_costs', return_value=dict(commission_price=2., slippage_price=2.))
    def test_range_cost_veto_is_enabled_by_default(self, mocked):
        blocks, _ = entry_check(dict(direction='BUY'), self.ticks(), now=335,
            plan=dict(required_bars=3, after_epoch=None), cost_path='unused')
        self.assertTrue(any('estimated round-trip cost' in block for block in blocks))

    def ticks(self):
        return [dict(timestamp=stamp, bid=4000+stamp*.1, ask=4000.02+stamp*.1)
                for stamp in range(120, 336)]

    @patch('services.research.gold_s30_execution.load_costs', return_value=dict(commission_price=.01, slippage_price=.02))
    def test_staged_counts_and_fresh_additions(self, mocked):
        for count in (3, 5, 6):
            blocks, report = entry_check(dict(direction='BUY'), self.ticks(), now=335,
                plan=dict(required_bars=count, after_epoch=None), cost_path='unused')
            self.assertEqual(blocks, [])
            self.assertEqual(len(report['bars']), count)
        blocks, _ = entry_check(dict(direction='BUY'), self.ticks(), now=335,
            plan=dict(required_bars=5, after_epoch=330), cost_path='unused')
        self.assertTrue(blocks)

    @patch('services.research.gold_s30_execution.load_costs', return_value=dict(commission_price=.01, slippage_price=.02))
    def test_opposing_advisor_is_blocked(self, mocked):
        blocks, _ = entry_check(dict(direction='SELL'), self.ticks(), now=335,
            plan=dict(required_bars=3, after_epoch=None), cost_path='unused')
        self.assertTrue(blocks)

    @patch('services.research.gold_s30_execution.load_costs', side_effect=ValueError('invalid'))
    def test_invalid_calibration_blocks_entries(self, mocked):
        blocks, _ = entry_check(dict(direction='BUY'), self.ticks(), now=335,
            plan=dict(required_bars=3, after_epoch=None), cost_path='unused')
        self.assertIn('invalid', blocks[0])

    def test_old_calibration_is_rejected(self):
        report = dict(as_of='2026-10-20T00:00:00+00:00', symbol='XAUUSD', currency='USD',
                      volume=.01, read_only=True, costs=dict(available=True, reconciled_pairs=30,
                      commission_price=0., slippage_price=.18))
        with patch('services.research.gold_s30_execution.Path.read_text', return_value=json.dumps(report)):
            with self.assertRaisesRegex(ValueError, 'older than 24 hours'):
                load_costs('unused', now=1792454400+172800)

    @patch('services.research.gold_s30_execution.load_costs', return_value=dict(
        commission_price=.01, slippage_price=.02, calibration_stale=True, calibration_age_seconds=172800))
    def test_stale_costs_do_not_block_valid_entry(self, mocked):
        blocks, report = entry_check(dict(direction='BUY'), self.ticks(), now=335,
            plan=dict(required_bars=3, after_epoch=None), cost_path='unused')
        self.assertEqual(blocks, [])
        self.assertTrue(report['cost_calibration']['stale'])

    @patch('services.research.gold_s30_execution.load_costs', return_value=dict(commission_price=0., slippage_price=0.))
    def test_closed_bar_mode_requires_directional_micro_follow_through(self, mocked):
        ticks = self.ticks()
        for tick in ticks[-6:]:
            tick.update(bid=4032.9, ask=4032.92)
        blocks, report = entry_check(dict(direction='BUY'), ticks, now=335,
            plan=dict(required_bars=3, after_epoch=None), cost_path='unused')
        self.assertTrue(any('follow-through' in block for block in blocks))
        self.assertTrue(report['fast_candidate']['micro_confirmation_enforced'])

    @patch('services.research.gold_s30_execution.load_costs', return_value=dict(commission_price=0., slippage_price=0.))
    def test_closed_bar_mode_still_blocks_actual_reversal(self, mocked):
        ticks = self.ticks()
        for tick in ticks[-6:]:
            tick.update(bid=4010., ask=4010.02)
        blocks, _ = entry_check(dict(direction='BUY'), ticks, now=335,
            plan=dict(required_bars=3, after_epoch=None), cost_path='unused')
        self.assertTrue(any('reversed' in block for block in blocks))


if __name__ == '__main__':
    unittest.main()
