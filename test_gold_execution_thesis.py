import unittest
from services.research.gold_execution_thesis import execution_thesis


class ExecutionThesisTests(unittest.TestCase):
    def test_failed_candidate_is_research_only_and_has_single_enable_setting(self):
        import ast
        from pathlib import Path
        from config import gold_consensus_settings as settings
        self.assertFalse(settings.EXECUTABLE_THESIS_ENABLED)
        self.assertTrue(settings.EXECUTABLE_THESIS_SHADOW_ENABLED)
        tree=ast.parse(Path('config/gold_consensus_settings.py').read_text(encoding='utf-8-sig'))
        assignments=[node for node in tree.body if isinstance(node,ast.Assign)
                     and any(isinstance(t,ast.Name) and t.id=='EXECUTABLE_THESIS_ENABLED' for t in node.targets)]
        self.assertEqual(len(assignments),1)
    def ticks(self, sign=1):
        return [dict(timestamp=i*.25,bid=4000+sign*i*.02,ask=4000.1+sign*i*.02) for i in range(162)]

    def assess(self, ticks=None, **kwargs):
        args=dict(now=40.25,direction='BUY',atr=2.,commission=.1,slippage=.2)
        args.update(kwargs)
        return execution_thesis(self.ticks() if ticks is None else ticks, **args)

    def test_two_sided_breakout_with_structural_stop(self):
        for side,sign in [('BUY',1),('SELL',-1)]:
            r=self.assess(self.ticks(sign),direction=side)
            self.assertTrue(r['allowed'],r['blocks'])
            self.assertGreater(sign*(r['levels']['entry_reference']-r['levels']['sl']),0)
            self.assertEqual(r['setup'],'S5_CONTINUATION_BREAK')

    def test_same_completed_event_keeps_identity_across_loop_times(self):
        first=self.assess()
        later=self.assess(now=40.4)
        self.assertEqual(first['setup_id'],later['setup_id'])

    def test_future_quotes_cannot_improve_current_decision(self):
        first=self.assess()
        future=self.assess(self.ticks()+[dict(timestamp=42.,bid=4500.,ask=4500.1)])
        self.assertEqual(first,future)

    def test_stale_sparse_flat_opposite_and_costly_data_fail(self):
        self.assertFalse(self.assess(self.ticks()[:-20])['allowed'])
        self.assertFalse(self.assess(self.ticks()[::16])['allowed'])
        flat=[dict(r,bid=4000.,ask=4000.1) for r in self.ticks()]
        self.assertFalse(self.assess(flat)['allowed'])
        self.assertFalse(self.assess(direction='SELL')['allowed'])
        self.assertFalse(self.assess(commission=10.)['allowed'])

    def test_heuristic_strength_never_substitutes_invalid_volatility(self):
        self.assertFalse(self.assess(atr=0.)['allowed'])
        self.assertFalse(self.assess(commission=True)['allowed'])
