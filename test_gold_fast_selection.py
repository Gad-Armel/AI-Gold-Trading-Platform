import unittest
from unittest.mock import patch

from services.research.gold_fast_selection import select_period


class FastSelectionTests(unittest.TestCase):
    @patch('services.research.gold_fast_selection.directional_signal', side_effect=[
        dict(bias='BUY', evidence=70, source_usable=True),
        dict(bias='SELL', evidence=70, source_usable=True)])
    @patch('services.research.gold_fast_selection.entry_check', return_value=([], {}))
    def test_reversal_skips_same_direction_and_scans_other_periods(self, check, signal):
        period, report = self.select(required_direction='SELL')
        self.assertEqual(period, 15)
        self.assertFalse(report['pinned'])
        self.assertFalse(report['candidates'][0]['eligible'])
        self.assertTrue(report['candidates'][1]['eligible'])

    @patch('services.research.gold_fast_selection.directional_signal', return_value=dict(
        bias='SELL', evidence=70, source_usable=True))
    @patch('services.research.gold_fast_selection.entry_check', return_value=(['cost'], {}))
    def test_opposite_direction_does_not_bypass_confirmations(self, check, signal):
        _, report = self.select(required_direction='SELL')
        self.assertTrue(all(not c['eligible'] for c in report['candidates']))

    @patch('services.research.gold_fast_selection.directional_signal', return_value=dict(bias='BUY', evidence=70, source_usable=True))
    @patch('services.research.gold_fast_selection.entry_check', return_value=([], {}))
    def test_over_budget_candidate_does_not_hide_next_feasible_period(self, check, signal):
        from unittest.mock import Mock
        risk = Mock(side_effect=[['Stop exceeds risk budget'], []])
        period, report = self.select(risk_evaluator=risk)
        self.assertEqual(period, 15)
        self.assertIn('risk budget', report['candidates'][0]['blocks'][0])
        self.assertEqual(risk.call_count, 2)

    @patch('services.research.gold_fast_selection.directional_signal', return_value=dict(bias='BUY', evidence=70, source_usable=True))
    @patch('services.research.gold_fast_selection.entry_check', return_value=([], {}))
    def test_unavailable_risk_never_marks_a_candidate_eligible(self, check, signal):
        from unittest.mock import Mock
        _, report = self.select(risk_evaluator=Mock(side_effect=RuntimeError('offline')))
        self.assertTrue(all(not row['eligible'] for row in report['candidates']))

    @patch('services.research.gold_fast_selection.directional_signal', return_value=dict(bias='BUY', evidence=70, source_usable=True))
    @patch('services.research.gold_fast_selection.entry_check', return_value=([], {}))
    def test_existing_exposure_keeps_period_pinned_when_risk_fails(self, check, signal):
        period, report = self.select(held_period=5, risk_evaluator=lambda signal: ['budget'])
        self.assertEqual(period, 5)
        self.assertFalse(report['candidates'][0]['eligible'])
        self.assertEqual(len(report['candidates']), 1)

    def select(self, **kwargs):
        return select_period([], now=1000, bid=4000., ask=4000.2, atr=2.,
                             cost_path='unused', account=None, **kwargs)

    @patch('services.research.gold_fast_selection.directional_signal', return_value=dict(bias='BUY', evidence=70, source_usable=True))
    @patch('services.research.gold_fast_selection.entry_check', side_effect=[(['cost'], {}), ([], {})])
    def test_uses_s15_when_s5_not_feasible(self, check, signal):
        period, report = self.select()
        self.assertEqual(period, 15)
        self.assertEqual(report['selected'], 'S15')
        self.assertEqual(check.call_count, 2)

    @patch('services.research.gold_fast_selection.directional_signal', return_value=dict(bias='BUY', evidence=70, source_usable=True))
    @patch('services.research.gold_fast_selection.entry_check', return_value=([], {}))
    def test_shortest_feasible_and_pinned_exposure(self, check, signal):
        self.assertEqual(self.select()[0], 5)
        self.assertEqual(self.select(held_period=30)[0], 30)

    @patch('services.research.gold_fast_selection.directional_signal', return_value=dict(bias='WAIT', evidence=0, source_usable=False))
    @patch('services.research.gold_fast_selection.entry_check', return_value=(['no data'], {}))
    def test_no_candidates_never_appear_eligible(self, check, signal):
        period, report = self.select()
        self.assertEqual(period, 30)
        self.assertTrue(all(not candidate['eligible'] for candidate in report['candidates']))
        self.assertIn('No candidate passed', report['reason'])


if __name__ == '__main__':
    unittest.main()
