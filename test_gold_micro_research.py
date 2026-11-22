import unittest

import pandas as pd

from services.research.gold_s30_shadow import fast_candidate
from services.research.gold_tick_markout import executable_markout, validate_ticks


class MicroResearchTests(unittest.TestCase):
    def test_research_cli_writes_explicit_non_backtest_report(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from tools.research_gold_micro_markouts import main
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'ticks.csv'
            output = Path(directory)/'report.json'
            frame = pd.DataFrame([dict(timestamp=index*250, bid=100+index*.1,
                                      ask=100.2+index*.1) for index in range(520)])
            frame.to_csv(source, sep=';', header=False, index=False)
            with patch('sys.argv', ['research', str(source), '--commission-price', '.1',
                    '--slippage-price', '.2', '--output', str(output)]), patch('builtins.print'):
                main()
            report = json.loads(output.read_text())
            self.assertEqual(len(report['results']), 48)
            self.assertIn('NOT_STRATEGY_BACKTEST', report['role'])
            self.assertEqual(len(report['sha256']), 64)
            self.assertGreater(report['holdout_boundary'], report['first_epoch'])

    def frame(self, step=.1):
        return pd.DataFrame([dict(timestamp=index*.25, bid=100+index*step,
                                  ask=100.2+index*step) for index in range(50)])

    def mark(self, frame, direction='BUY', **kwargs):
        options = dict(horizon_seconds=1., latency_seconds=.25,
                       commission_price=.05, slippage_price=.1)
        options.update(kwargs)
        return executable_markout(validate_ticks(frame), 1., direction, **options)

    def test_flat_market_both_legs_lose_spread_and_costs(self):
        result = self.mark(self.frame(0))
        self.assertAlmostEqual(result['main_net_price'], -.35)
        self.assertAlmostEqual(result['inverse_net_price'], -.35)

    def test_buy_and_inverse_use_executable_sides_not_midpoint(self):
        result = self.mark(self.frame())
        self.assertAlmostEqual(result['entry_epoch'], 1.25)
        self.assertAlmostEqual(result['exit_epoch'], 2.5)
        self.assertAlmostEqual(result['main_net_price'], .15)
        self.assertAlmostEqual(result['inverse_net_price'], -.85)
        sell = self.mark(self.frame(), 'SELL')
        self.assertAlmostEqual(sell['main_net_price'], result['inverse_net_price'])

    def test_missing_future_and_feed_gaps_are_not_filled(self):
        self.assertIsNone(self.mark(self.frame().iloc[:6]))
        self.assertIsNone(self.mark(self.frame().drop(range(6, 40))))

    def test_invalid_and_out_of_order_input_rejected(self):
        with self.assertRaises(ValueError):
            validate_ticks(self.frame().iloc[::-1])
        frame = self.frame()
        frame.loc[0, 'ask'] = 1.
        with self.assertRaises(ValueError):
            validate_ticks(frame)
        with self.assertRaises(ValueError):
            self.mark(self.frame(), slippage_price=-1.)

    def test_duplicate_ticks_do_not_create_observations(self):
        frame = self.frame()
        self.assertEqual(len(validate_ticks(pd.concat([frame.iloc[:1], frame]))), len(frame))

    def test_midpoint_movement_requires_both_quote_sides(self):
        bars = [dict(time=index*5, open=100., close=100.6, high=102., low=98.) for index in range(3)]
        for direction, bid_step, ask_step, expected in (
                ('BUY', 0., .1, False), ('SELL', -.1, 0., False),
                ('BUY', .1, .1, True), ('SELL', -.1, -.1, True)):
            ticks = [(index, 100+bid_step*index, 100.2+ask_step*index) for index in range(7)]
            result = fast_candidate(ticks, bars, now=6., direction=direction,
                                    commission_price=0., slippage_price=0.)
            self.assertEqual(result['executable_confirmation'], expected)
            if not expected:
                self.assertTrue(any('Both bid and ask' in block for block in result['blocks']))

    def test_micro_override_reports_warning_without_silent_enforcement(self):
        bars = [dict(time=index*5, open=100., close=100.6, high=102., low=98.) for index in range(3)]
        ticks = [(index, 100., 100.2+.1*index) for index in range(7)]
        result = fast_candidate(ticks, bars, now=6., direction='BUY', commission_price=0.,
                                slippage_price=0., require_micro_confirmation=False)
        self.assertFalse(result['executable_confirmation'])
        self.assertFalse(any('Both bid and ask' in block for block in result['blocks']))
        self.assertTrue(any('Both bid and ask' in warning for warning in result['warnings']))


if __name__ == '__main__':
    unittest.main()
