import unittest
from unittest.mock import patch

from services.research.gold_s30_shadow import s30_observation
from services.research.gold_s30_execution import directional_signal, entry_check
from services.research.gold_horizon_policy import build_horizon_decisions
from test_gold_horizon_policy import _consensus


class S15Tests(unittest.TestCase):
    def ticks(self):
        return [dict(timestamp=stamp, bid=4000+stamp*.1, ask=4000.02+stamp*.1)
                for stamp in range(120, 231)]

    def test_completed_s15_boundaries_and_stages(self):
        for count in (3, 5, 6):
            report = s30_observation(self.ticks(), now=230, period_seconds=15, bar_count=count)
            self.assertTrue(report['available'])
            self.assertEqual(report['timeframe'], 'S15')
            self.assertEqual(len(report['bars']), count)
            self.assertEqual(report['bars'][-1]['time'], 210)
            self.assertEqual(report['bars'][0]['time'], 225-15*count)
            self.assertTrue(report['fast_candidate']['setup_id'].startswith('S15:'))

    @patch('services.research.gold_s30_execution.load_costs', return_value=dict(commission_price=0., slippage_price=.01))
    def test_s15_add_requires_fresh_s15_close(self, mocked):
        blocks, report = entry_check(dict(direction='BUY'), self.ticks(), now=230,
            period_seconds=15, plan=dict(required_bars=5, after_epoch=225), cost_path='unused')
        self.assertTrue(any('fresh' in block for block in blocks))
        self.assertEqual(report['entry_timeframe'], 'S15')

    def test_s15_policy_identity_and_levels(self):
        ticks = self.ticks()
        signal = directional_signal(ticks, now=230, bid=ticks[-1]['bid'], ask=ticks[-1]['ask'],
                                    atr=2., period_seconds=15)
        decisions = build_horizon_decisions(_consensus(('SELL', 90), ('SELL', 90), ('SELL', 90)),
            scalp_signal=signal, market_context={'SCALP': dict(available=True, atr=2.,
            bid=ticks[-1]['bid'], ask=ticks[-1]['ask'])})
        self.assertTrue(decisions['SCALP']['allowed'])
        self.assertEqual(decisions['SCALP']['entry_mode'], 'S15_PRIMARY')
        self.assertEqual(decisions['SCALP']['levels']['source'], 'S15_STRUCTURE')

    def test_no_arbitrary_timeframe_or_fabricated_bars(self):
        with self.assertRaises(ValueError):
            s30_observation(self.ticks(), now=230, period_seconds=2)
        ticks = [tick for tick in self.ticks() if not 185 <= tick['timestamp'] <= 195]
        self.assertFalse(s30_observation(ticks, now=230, period_seconds=15)['available'])


if __name__ == '__main__':
    unittest.main()
