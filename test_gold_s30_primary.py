import unittest
from copy import deepcopy

from services.research.gold_horizon_policy import build_horizon_decisions
from services.research.gold_s30_execution import directional_signal
from test_gold_horizon_policy import _consensus


class S30PrimaryTests(unittest.TestCase):
    def signal(self, sell=False):
        sign = -1 if sell else 1
        ticks = [dict(timestamp=stamp, bid=4000+sign*stamp*.1, ask=4000.02+sign*stamp*.1)
                 for stamp in range(120, 336)]
        return directional_signal(ticks, now=335, bid=ticks[-1]['bid'], ask=ticks[-1]['ask'], atr=2.)

    def build(self, consensus, signal, news=None):
        return build_horizon_decisions(consensus, news_risk=news, scalp_signal=signal,
            market_context={'SCALP': dict(available=True, atr=2., bid=4000., ask=4000.2)})

    def test_independent_s30_bias_and_structural_levels(self):
        for sell in (False, True):
            signal = self.signal(sell)
            reference = signal['levels']['entry_reference']
            if sell:
                self.assertGreater(signal['levels']['sl'], reference)
                self.assertLess(signal['levels']['tp1'], reference)
            else:
                self.assertLess(signal['levels']['sl'], reference)
                self.assertGreater(signal['levels']['tp1'], reference)

    def test_opposing_advisor_is_context_only_and_not_mutated(self):
        consensus = _consensus(('SELL', 95), ('SELL', 95), ('SELL', 90))
        original = deepcopy(consensus)
        decisions = self.build(consensus, self.signal())
        self.assertTrue(decisions['SCALP']['allowed'])
        self.assertEqual(decisions['SCALP']['direction'], 'BUY')
        self.assertEqual(decisions['SCALP']['entry_mode'], 'S30_PRIMARY')
        self.assertEqual(decisions['SCALP']['levels']['source'], 'S30_STRUCTURE')
        self.assertEqual(consensus, original)

    def test_news_still_blocks(self):
        decisions = self.build(_consensus(('BUY', 90), ('BUY', 90), ('BUY', 90)), self.signal(),
            dict(allowed=False, block_reasons=['Major news'], active_events=[]))
        self.assertFalse(decisions['SCALP']['allowed'])

    def test_bad_ticks_cannot_authorize_entry(self):
        signal = directional_signal([], now=335, bid=4000., ask=4000.2, atr=2.)
        decisions = self.build(_consensus(('BUY', 90), ('BUY', 90), ('BUY', 90)), signal)
        self.assertFalse(decisions['SCALP']['allowed'])

    def test_missing_atr_rejected(self):
        self.assertFalse(directional_signal([], now=335, bid=4000., ask=4000.2, atr=0.)['source_usable'])

    def test_missing_ticks_show_input_failure_before_generic_weakness(self):
        signal = directional_signal([], now=335, bid=4000., ask=4000.2, atr=2.)
        decision = self.build(_consensus(('WAIT', 0), ('WAIT', 0), ('WAIT', 0)), signal)['SCALP']
        self.assertFalse(decision['allowed'])
        self.assertIn('No tick history', decision['blocks'][0])


if __name__ == '__main__':
    unittest.main()
