import unittest
from datetime import datetime, timezone, timedelta
from services.research.gold_candle_input_health import candle_input_health, guard_candle_report


class CandleInputHealthTests(unittest.TestCase):
    def test_unusable_primary_is_rejected_by_actual_consensus_policy(self):
        from services.research.gold_advisory_consensus import build_gold_advisory_consensus
        from services.research.gold_horizon_policy import build_horizon_decisions
        now = datetime.now(timezone.utc)
        report = dict(generated_at=now.isoformat(), bid=100, ask=100.2,
            horizons=dict(SCALP=dict(bias='BUY', directional_score=99,
                valid_until=(now+timedelta(minutes=5)).isoformat(), levels=dict(sl=99, tp1=102))))
        guarded = guard_candle_report(report, dict(available=False, entry_blocks=['M5 stale']))
        missing = dict(available=False, generated_at=now.isoformat(), horizons={})
        consensus = build_gold_advisory_consensus(guarded, missing, missing)
        decision = build_horizon_decisions(consensus)['SCALP']
        self.assertFalse(decision['allowed'])
        self.assertFalse(consensus['horizons']['SCALP']['advisors']['MT5_CANDLES']['source_usable'])

    def frames(self, offset=0):
        return {name: [dict(time=3600-seconds+offset, open=100, high=102, low=99, close=101),
                       dict(time=3600+offset, open=101, high=102, low=100, close=101)]
                for name, seconds in (('M1', 60), ('M5', 300), ('M15', 900))}

    def test_fresh_inputs_and_broker_offset(self):
        for offset in (0, 10800):
            self.assertTrue(candle_input_health(self.frames(offset), now=3601, offset=offset)['available'])

    def test_report_refresh_cannot_rejuvenate_stale_higher_timeframe(self):
        frames = self.frames()
        frames['M5'] = [dict(frames['M5'][0], time=2700), dict(frames['M5'][1], time=3000)]
        health = candle_input_health(frames, now=3606, offset=0)
        self.assertFalse(health['available'])
        report = dict(generated_at='fresh', horizons=dict(SCALP=dict(bias='BUY', directional_score=99)))
        guarded = guard_candle_report(report, health)
        self.assertFalse(guarded['horizons']['SCALP']['source_usable'])
        self.assertNotIn('source_usable', report['horizons']['SCALP'])

    def test_forming_bar_is_not_a_completed_confirmation(self):
        frames = self.frames()
        frames['M15'] = frames['M15'][1:]
        self.assertFalse(candle_input_health(frames, now=3601, offset=0)['available'])

    def test_future_candles_cannot_hide_behind_a_fresh_completed_bar(self):
        frames = self.frames()
        frames['M1'].append(dict(time=3660, open=101, high=102, low=100, close=101))
        self.assertFalse(candle_input_health(frames, now=3601, offset=0)['available'])

    def test_bounded_rollover_grace_does_not_mask_missing_next_bar(self):
        frames = self.frames()
        frames['M1'] = frames['M1'][:1]
        self.assertTrue(candle_input_health(frames, now=3664.9, offset=0)['available'])
        self.assertFalse(candle_input_health(frames, now=3665, offset=0)['available'])

    def test_healthy_inputs_do_not_override_unavailable_report(self):
        report = dict(available=False, horizons=dict(SCALP=dict(source_usable=False)))
        guarded = guard_candle_report(report, candle_input_health(self.frames(), now=3601, offset=0))
        self.assertFalse(guarded['available'])
        self.assertFalse(guarded['horizons']['SCALP']['source_usable'])
