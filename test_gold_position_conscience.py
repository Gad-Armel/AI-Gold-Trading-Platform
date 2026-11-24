"""Coverage for risk-anchored exits and the position conscience."""
import unittest

from config import gold_consensus_settings as settings
from services.research.gold_adaptive_exit import evaluate_adaptive_exit, risk_price_distance
from services.research.gold_position_conscience import (
    assess_position_conscience, conviction_collapse, giveback_scale,
)


class RiskAnchoredExitTests(unittest.TestCase):
    """The regression that motivated R anchoring.

    Live M5/M15/H1 ATR on this broker (2026-09) was $5.71 / $9.25 / $21.36
    while the lane stops were $4 / $2 / $4. An ATR-multiple trail therefore
    armed at 1.4x, 4.6x and 8x the risk budgeted for the trade and could never
    fire before the stop did.
    """

    def setUp(self):
        self.context = dict(available=True, horizon='SCALP', atr=5.71, trend=1., momentum=1.,
                            close=4002., previous_low=3990., previous_high=4010.)
        self.positions = [dict(ticket=1, direction='BUY', volume=.01, entry_price=4000.)]
        self.decision = dict(allowed=True, direction='BUY')
        self.state = {}

    def evaluate(self, now=0., bid=4000., spread=.24, conscience=None, lane='SCALP'):
        return evaluate_adaptive_exit(
            self.decision, self.positions, self.context, self.state, now=now, bid=bid,
            ask=bid + spread, feed_age=0., config=settings.ADAPTIVE_EXIT_CONFIG[lane],
            risk_usd=4.0, contract_size=100., conscience=conscience)

    def test_every_lane_arms_inside_its_own_risk_budget(self):
        for lane, config in settings.ADAPTIVE_EXIT_CONFIG.items():
            with self.subTest(lane=lane):
                self.assertLess(float(config['trail_arm_r']), 1.0,
                                f'{lane} trail cannot arm beyond its own stop')
                self.assertLess(float(config['trail_giveback_r']), 1.0)
                self.assertLessEqual(float(config['trail_arm_r']),
                                     float(config['breakeven_arm_r']))

    def test_risk_unit_is_price_distance_not_dollars(self):
        # 0.01 lot x 100oz = 1oz, so a $4 stop is a $4 price distance here.
        self.assertAlmostEqual(risk_price_distance(4.0, .01, 100.), 4.0)
        self.assertAlmostEqual(risk_price_distance(4.0, .02, 100.), 2.0)
        self.assertEqual(risk_price_distance(4.0, 0., 100.), 0.0)
        self.assertEqual(risk_price_distance(0., .01, 100.), 0.0)

    def test_giveback_fires_well_inside_one_atr(self):
        """The old trail needed +$5.71 before arming; this arms at +$1.60."""
        self.evaluate(bid=4002.)           # peak +2.00 == 0.50R
        result = self.evaluate(now=10., bid=4000.4)
        self.assertTrue(result['close'])
        self.assertLess(result['giveback_distance'], self.context['atr'])
        self.assertTrue(result['trail_armed'])

    def test_protected_winner_cannot_become_a_loser(self):
        self.evaluate(bid=4002.5)          # peak +2.50 >= 0.60R breakeven arm
        self.assertTrue(self.state['breakeven_armed'])
        result = self.evaluate(now=5., bid=4000.05)
        self.assertTrue(result['close'])
        self.assertIn('breakeven', result['reason'].lower())

    def test_breakeven_ratchet_does_not_arm_on_a_small_move(self):
        self.evaluate(bid=4001.)           # peak +1.00 < 0.60R
        self.assertFalse(self.state.get('breakeven_armed'))
        self.assertFalse(self.evaluate(now=5., bid=4000.05)['close'])

    def test_giveback_never_sits_inside_dealing_noise(self):
        self.evaluate(bid=4002.)
        wide = self.evaluate(now=5., bid=4001.9, spread=3.0)
        self.assertGreaterEqual(wide['giveback_distance'],
                                float(settings.ADAPTIVE_GIVEBACK_SPREAD_FLOOR) * 3.0)

    def test_conviction_scales_the_giveback_within_bounds(self):
        self.evaluate(bid=4002.)
        tight = self.evaluate(now=5., bid=4001.9,
                              conscience=dict(available=True, alignment=-1., coverage=1., conviction=0.))
        self.state.clear()
        self.evaluate(bid=4002.)
        loose = self.evaluate(now=5., bid=4001.9,
                              conscience=dict(available=True, alignment=1., coverage=1., conviction=1.))
        self.assertLess(tight['giveback_distance'], loose['giveback_distance'])
        self.assertAlmostEqual(tight['giveback_scale'], settings.ADAPTIVE_GIVEBACK_MIN_SCALE)
        self.assertAlmostEqual(loose['giveback_scale'], settings.ADAPTIVE_GIVEBACK_MAX_SCALE)


class ConscienceScoringTests(unittest.TestCase):
    def agreeing(self, direction='BUY'):
        sign = 1 if direction == 'BUY' else -1
        return dict(
            direction=direction, horizon='SCALP',
            decision=dict(dominant_bias=direction, evidence=90., entry_threshold=82., exit_threshold=58.),
            context=dict(available=True, trend=sign * 1.2, momentum=sign * 1.0,
                         close=4002., previous_low=3990., previous_high=4010.,
                         structure_research={'regime': 'TREND_UP' if sign == 1 else 'TREND_DOWN'}),
            micro_flow=dict(available=True, pressure=sign, reversal_risk=0.),
            flow=dict(close=False, move=1.5, threshold=.5, peak_move=1.5),
            cross_market=dict(available=True, gold_bias=direction, dollar_pressure_z=2.),
            learned=dict(available=True, continuation_usd={direction: 1.0}, minimum_edge_usd=.25),
            economic=dict(bias=direction, score=.8, quality=.9),
            news_risk=dict(allowed=True, active_events=[]),
        )

    def test_full_agreement_scores_high_with_full_coverage(self):
        result = assess_position_conscience(**self.agreeing())
        self.assertTrue(result['available'])
        self.assertGreater(result['conviction'], .85)
        self.assertAlmostEqual(result['coverage'], 1.0)
        self.assertEqual(result['leading_concerns'], [])

    def test_continuous_entry_floor_is_not_full_exit_conviction(self):
        from services.research.gold_position_conscience import _consensus_vote
        decision = dict(dominant_bias='BUY', evidence=16, entry_threshold=15,
                        exit_threshold=15, continuous_directional_entries=True)
        low = _consensus_vote(decision, 'BUY')[0]
        decision['evidence'] = 76
        medium = _consensus_vote(decision, 'BUY')[0]
        decision['evidence'] = 100
        high = _consensus_vote(decision, 'BUY')[0]
        self.assertLess(low, .02)
        self.assertLess(low, medium)
        self.assertLess(medium, high)
        self.assertEqual(high, 1)

    def test_wholesale_contradiction_collapses_conviction(self):
        payload = self.agreeing()
        payload['decision']['dominant_bias'] = 'SELL'
        payload['context'].update(trend=-1.2, momentum=-1.0, close=3985.)
        payload['context']['structure_research']['regime'] = 'TREND_DOWN'
        payload['micro_flow'] = dict(available=True, pressure=-1., reversal_risk=1.)
        payload['flow'] = dict(close=True, move=-1.5, threshold=.5, peak_move=1.5)
        payload['cross_market']['gold_bias'] = 'SELL'
        payload['learned']['continuation_usd'] = {'BUY': -1.0}
        payload['economic']['bias'] = 'SELL'
        result = assess_position_conscience(**payload)
        self.assertLess(result['conviction'], .15)
        self.assertTrue(result['leading_concerns'])

    def test_missing_sources_lower_coverage_without_faking_agreement(self):
        result = assess_position_conscience(
            direction='BUY', horizon='SCALP',
            decision=dict(dominant_bias='BUY', evidence=90., entry_threshold=82., exit_threshold=58.))
        self.assertTrue(result['available'])
        self.assertLess(result['coverage'], .35)
        unusable = [i for i in result['contributions'] if not i['usable']]
        self.assertGreaterEqual(len(unusable), 4)

    def test_no_usable_source_is_reported_not_guessed(self):
        result = assess_position_conscience(direction='BUY', horizon='SCALP')
        self.assertFalse(result['available'])
        self.assertEqual(result['coverage'], 0.0)

    def test_direction_is_required(self):
        self.assertFalse(assess_position_conscience(direction='WAIT', horizon='SCALP')['available'])

    def test_thin_coverage_can_tighten_but_never_widen(self):
        thin = dict(available=True, alignment=1., coverage=.2, conviction=1.)
        self.assertEqual(giveback_scale(thin), 1.0)
        thin_adverse = dict(available=True, alignment=-1., coverage=.2, conviction=0.)
        self.assertLess(giveback_scale(thin_adverse), 1.0)

    def test_scale_is_bounded_and_safe_by_default(self):
        self.assertEqual(giveback_scale({}), 1.0)
        self.assertEqual(giveback_scale(dict(available=True)), 1.0)
        for alignment in (-1., -.5, 0., .5, 1.):
            scale = giveback_scale(dict(available=True, alignment=alignment, coverage=1., conviction=.5))
            self.assertGreaterEqual(scale, settings.ADAPTIVE_GIVEBACK_MIN_SCALE)
            self.assertLessEqual(scale, settings.ADAPTIVE_GIVEBACK_MAX_SCALE)


class ConvictionCollapseTests(unittest.TestCase):
    def setUp(self):
        self.state = {}
        self.collapsed = dict(available=True, conviction=.10)

    def call(self, now, conscience=None, profit_r=.5, signature=('a',)):
        return conviction_collapse(conscience or self.collapsed, self.state, now=now,
                                   profit_r=profit_r, horizon='SCALP', position_signature=signature)

    def test_collapse_must_persist(self):
        self.assertFalse(self.call(0)[0])
        self.assertFalse(self.call(5)[0])
        closed, reason = self.call(9)
        self.assertTrue(closed)
        self.assertIn('Conviction collapsed', reason)

    def test_recovery_resets_the_timer(self):
        self.call(0)
        self.call(5, conscience=dict(available=True, conviction=.8))
        self.assertFalse(self.call(9)[0])
        self.assertTrue(self.call(18)[0])

    def test_losing_position_is_left_to_its_stop(self):
        """This banks profit; it must never pre-empt the configured stop."""
        for now in (0, 5, 20, 40):
            self.assertFalse(self.call(now, profit_r=-.5)[0])

    def test_new_position_does_not_inherit_the_collapse(self):
        self.call(0)
        self.call(5)
        self.assertFalse(self.call(9, signature=('b',))[0])

    def test_unavailable_conscience_never_closes(self):
        for now in (0, 20, 40):
            self.assertFalse(self.call(now, conscience=dict(available=False))[0])


if __name__ == '__main__':
    unittest.main()
