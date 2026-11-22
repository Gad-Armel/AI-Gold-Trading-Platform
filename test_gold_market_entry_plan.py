import unittest
from services.research.gold_market_entry_plan import market_entry_plan


class MarketEntryPlanTests(unittest.TestCase):
    def context(self, **changes):
        result=dict(available=True, atr=2., bar_id='1970-01-01T00:02:00+00:00',
                    trend=.2, momentum=.1, structure_research=dict(regime='TREND_UP'))
        result.update(changes)
        return result

    def ticks(self, direction=1):
        return [dict(timestamp=120+i*.5, bid=4000+direction*i*.02,
                     ask=4000.2+direction*i*.02) for i in range(121)]

    def plan(self, ticks=None, context=None, **changes):
        args=dict(now=180., direction='BUY', commission=.1, slippage=.2)
        args.update(changes)
        return market_entry_plan(self.ticks() if ticks is None else ticks,
                                 self.context() if context is None else context, **args)

    def test_structural_stop_uses_executable_sides_and_never_widens_to_budget(self):
        for direction, sign in [('BUY',1),('SELL',-1)]:
            rows=self.ticks(sign)
            result=self.plan(rows,direction=direction)
            self.assertTrue(result['allowed'],result['blocks'])
            last30=[r for r in rows if r['timestamp']>=150]
            pivot=min(r['bid'] for r in last30) if sign==1 else max(r['ask'] for r in last30)
            expected=pivot-sign*max(.5*.2,.1*2.)
            self.assertAlmostEqual(result['levels']['sl'],expected)
            self.assertGreater(result['executable_stop_room_price'],0.)
            self.assertIn('Synthetic',result['analysis_target_role'])

    def test_future_prefix_invariance(self):
        before=self.plan()
        with_future=self.plan(self.ticks()+[dict(timestamp=181.,bid=1.,ask=5000.)])
        self.assertEqual(before,with_future)

    def test_clear_opposition_veto_and_neutral_short_move_is_allowed(self):
        rows=self.ticks()
        # Final three seconds fall on both executable sides, despite prior rise.
        for i,row in enumerate(rows[-7:]):
            row.update(bid=4002.28-i*.06,ask=4002.48-i*.06)
        opposed=self.plan(rows)
        self.assertTrue(opposed['direct_opposition'])
        self.assertFalse(opposed['allowed'])
        self.assertIn('Both executable sides',opposed['blocks'][0])
        neutral=self.ticks()
        for row in neutral[-7:]:
            row.update(bid=4002.28,ask=4002.48)
        result=self.plan(neutral)
        self.assertFalse(result['direct_opposition'])
        self.assertTrue(result['allowed'],result['blocks'])

    def test_same_completed_bar_identity_does_not_rearm_with_loop_time(self):
        first=self.plan()
        later=self.plan(now=181.)
        self.assertEqual(first['setup_id'],later['setup_id'])

    def test_stale_sparse_missing_and_malformed_data_rejected(self):
        self.assertFalse(self.plan(self.ticks()[:-7])['available'])
        self.assertFalse(self.plan(self.ticks()[::10])['available'])
        self.assertFalse(self.plan([])['available'])
        bad=self.ticks()+[dict(timestamp=179.9,bid=4000.,ask=3999.)]
        self.assertFalse(self.plan(bad)['available'])
        self.assertFalse(self.plan([dict(timestamp=178.,bid=4000.,ask=4000.2)])['available'])

    def test_maximum_risk_and_cost_room_reject_without_mutating_stop(self):
        result=self.plan(maximum_risk=1.)
        self.assertFalse(result['allowed'])
        self.assertTrue(any('maximum trade-risk' in block for block in result['blocks']))
        normal=self.plan()
        self.assertEqual(result['levels']['sl'],normal['levels']['sl'])
        result=self.plan(commission=.8,slippage=.2)
        self.assertFalse(result['allowed'])
        self.assertTrue(any('insufficient room' in block for block in result['blocks']))

    def test_completed_context_is_required_and_inputs_are_explicit(self):
        for bar in ('1970-01-01T00:03:00+00:00','1970-01-01T00:00:00+00:00',
                    '1970-01-01T00:02:00',None):
            self.assertFalse(self.plan(context=self.context(bar_id=bar))['available'])
        self.assertFalse(self.plan(commission=True)['available'])
        self.assertFalse(self.plan(maximum_risk=float('nan'))['available'])


if __name__=='__main__':
    unittest.main()
