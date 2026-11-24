import unittest
from unittest.mock import patch

from services.research.gold_graded_trigger import graded_trigger
from services.research.gold_trigger_funnel import observe_funnel
from services.research.gold_fast_selection import select_period
from services.research.gold_trigger_labels import observe_labels


class GradedTriggerTests(unittest.TestCase):
    def test_counterfactual_labels_wait_for_future_quote_and_charge_costs(self):
        state = {}
        decision = dict(direction='BUY', stop_loss=3999., s30_entry=dict(available=True,
            fast_candidate=dict(direction='BUY', setup_id='S1:100:BUY')))
        args = dict(feed_age=0., bid=4000., ask=4000.2)
        report = observe_labels(state, decision, now=100., **args)
        self.assertEqual(report['pending'], 1)
        self.assertNotIn('entry', state['pending']['S1:100:BUY'])
        observe_labels(state, decision, now=100.2, **args)
        self.assertNotIn('entry', state['pending']['S1:100:BUY'])
        observe_labels(state, decision, now=100.5, bid=4000., ask=4000.2, feed_age=.4)
        self.assertNotIn('entry', state['pending']['S1:100:BUY'])
        observe_labels(state, decision, now=100.4, **args)
        report = observe_labels(state, {}, now=101., bid=3998., ask=3998.2, feed_age=0.)
        self.assertEqual(report['groups']['NOT_ATTEMPTED']['labels'], 1)
        self.assertLess(report['groups']['NOT_ATTEMPTED']['mean_net_r'], -1.)
        self.assertFalse(report['execution_enabled'])

    def test_stale_quotes_do_not_label_or_create_triggers(self):
        report = observe_labels({}, {}, now=100., bid=4000., ask=4000.2, feed_age=3.)
        self.assertEqual(report['pending'], 0)
        self.assertEqual(report['groups'], {})

    def test_missing_structure_cannot_be_promoted_by_score(self):
        report = graded_trigger(dict(direction='BUY', evidence=100), {},
            dict(available=True, pressure=1., efficiency=1.), bid=4000., ask=4000.4)
        self.assertEqual(report['suggested_tier'], 'NO_SETUP')
        self.assertFalse(report['execution_enabled'])
        self.assertIsNone(report['calibrated_probability'])

    def test_reduced_size_does_not_round_up_minimum_lot(self):
        report = graded_trigger(dict(direction='BUY', evidence=20),
            dict(available=True, structure_research=dict(downside_sweep=True)),
            dict(available=True, pressure=.7, efficiency=.7), bid=4000., ask=4000.4)
        self.assertEqual(report['suggested_tier'], 'REDUCED')
        self.assertFalse(report['reduced_size_representable'])
        self.assertEqual(report['actual_lot_unchanged'], .01)

    def test_invalid_quotes_fail_closed_for_research(self):
        report = graded_trigger({}, {}, {}, bid=float('nan'), ask=4000.)
        self.assertFalse(report['available'])

    def test_funnel_deduplicates_and_does_not_count_eligible_as_filled(self):
        state = {}
        decision = dict(direction='BUY', allowed=True, blocks=[], s30_entry=dict(available=True,
            fast_candidate=dict(direction='BUY', setup_id='S5:100:BUY')))
        for _ in range(10):
            report = observe_funnel(state, decision, timing_blocks=[])
        self.assertEqual(report['window_unique_setups'], 1)
        self.assertEqual(report['request_attempts'], 0)
        self.assertEqual(report['reported_execution_rate'], 0.)
        report = observe_funnel(state, decision, timing_blocks=[], attempted=True,
            result=dict(success=True, execution_metrics=dict(state='REPORTED_DONE')))
        report = observe_funnel(state, decision, timing_blocks=['Spacing'])
        self.assertEqual(report['reported_done_setups'], 1)
        self.assertIsNone(report['confirmed_fill_rate'])
        self.assertIsNone(report['acceptance_target'])

    def test_unavailable_feed_is_not_a_broker_rejection(self):
        report = observe_funnel({}, dict(direction='WAIT'), timing_blocks=['Coverage'])
        self.assertEqual(report['window_unique_setups'], 0)
        self.assertEqual(report['stages'], {})

    @patch('services.research.gold_fast_selection.entry_check')
    @patch('services.research.gold_fast_selection.directional_signal')
    def test_micro_falls_back_without_weakening_coverage(self, signal, check):
        signal.side_effect = lambda *args, **kwargs: dict(bias='BUY', source_usable=True, evidence=80)
        check.side_effect = lambda *args, **kwargs: (['Coverage'] if kwargs['period_seconds'] == 1 else [], {})
        period, report = select_period([], now=1000, bid=4000., ask=4000.4, atr=2.,
            cost_path='unused', account=None, include_s1=True)
        self.assertEqual(period, 5)
        self.assertEqual([row['timeframe'] for row in report['candidates']], ['S1', 'S5'])

    @patch('services.research.gold_fast_selection.entry_check', return_value=([], {}))
    @patch('services.research.gold_fast_selection.directional_signal',
           return_value=dict(bias='BUY', source_usable=True, evidence=80))
    def test_micro_pins_open_s1_and_auto_default_unchanged(self, signal, check):
        args = dict(now=1000, bid=4000., ask=4000.4, atr=2., cost_path='unused', account=None)
        period, _ = select_period([], **args, include_s1=True, held_period=1)
        self.assertEqual(period, 1)
        period, _ = select_period([], **args)
        self.assertEqual(period, 5)


if __name__ == '__main__':
    unittest.main()
