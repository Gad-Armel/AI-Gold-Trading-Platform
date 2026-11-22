from contextlib import redirect_stdout
import io
import unittest

from run_gold_consensus_bot import _print_cycle


class MainDisplayTests(unittest.TestCase):
    def test_secondary_context_is_not_printed_as_a_trading_category(self):
        lane = dict(decision=dict(dominant_bias='WAIT', evidence=0, allowed=False), positions=[], status='WAIT')
        lanes = {name: dict(lane) for name in ('SCALP', 'INTRADAY', 'SWING')}
        output = io.StringIO()
        with redirect_stdout(output):
            _print_cycle(1, lanes, dict(realized=0, floating=0, total=0), 'demo')
        self.assertIn('SCALP', output.getvalue())
        self.assertNotIn('INTRADAY', output.getvalue())
        self.assertNotIn('SWING', output.getvalue())
        self.assertEqual(set(lanes), {'SCALP', 'INTRADAY', 'SWING'})
