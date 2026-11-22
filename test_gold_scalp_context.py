import unittest
from services.research.gold_scalp_context import scalp_context
from services.research.gold_horizon_policy import evaluate_entry_timing


class ScalpContextTests(unittest.TestCase):
    def view(self, bias, score=100, usable=True):
        return dict(dominant_bias=bias, evidence=score,
                    contributors=[dict(source_usable=usable, bias=bias)])

    def test_support_and_opposition_adjust_additions_without_flipping_scalp(self):
        decisions = dict(SCALP=self.view('BUY'), INTRADAY=self.view('BUY'), SWING=self.view('BUY'))
        context = scalp_context(decisions)
        self.assertEqual(context['addition_threshold_adjustment'], -5)
        decisions['SWING'] = self.view('SELL')
        self.assertEqual(scalp_context(decisions)['addition_threshold_adjustment'], 0)
        decisions['INTRADAY'] = self.view('SELL')
        self.assertEqual(scalp_context(decisions)['addition_threshold_adjustment'], 5)
        self.assertEqual(decisions['SCALP']['dominant_bias'], 'BUY')

    def test_stale_and_neutral_context_cannot_support_scalp(self):
        decisions = dict(SCALP=self.view('BUY'), INTRADAY=self.view('BUY', usable=False),
                         SWING=self.view('WAIT'))
        self.assertEqual(scalp_context(decisions)['addition_threshold_adjustment'], 0)

    def test_context_changes_addition_threshold_only(self):
        cfg = dict(minimum_signal_seconds=5, add_position_evidence=75, add_position_spacing_seconds=15)
        decision = dict(horizon='SCALP', allowed=True, evidence=72,
                        higher_timeframe_context=dict(addition_threshold_adjustment=-5))
        args = dict(signal_age_seconds=10, seconds_since_last_entry=20, lane_config=cfg)
        self.assertTrue(evaluate_entry_timing(decision, open_position_count=1, **args)[0])
        decision['higher_timeframe_context']['addition_threshold_adjustment'] = 5
        self.assertFalse(evaluate_entry_timing(decision, open_position_count=1, **args)[0])
        self.assertTrue(evaluate_entry_timing(decision, open_position_count=0, **args)[0])
