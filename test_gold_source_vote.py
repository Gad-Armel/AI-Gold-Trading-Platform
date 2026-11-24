import unittest
from services.research.gold_source_vote import source_vote, SOURCES


class SourceVoteTests(unittest.TestCase):
    def vote(self, votes, **kwargs):
        contributors = [dict(advisor=name, bias=bias, evidence=score, source_usable=usable)
                        for name, (bias, score, usable) in zip(SOURCES, votes)]
        return source_vote(dict(contributors=contributors, **kwargs),
            dict(available=True, bid=4000., ask=4000.2, atr=2.), now=1000.)

    def test_one_two_three_source_allowances(self):
        for count in (1, 2, 3):
            r = self.vote([('SELL', 80, True)]*count+[('WAIT', 0, True)]*(3-count))
            self.assertTrue(r['allowed'])
            self.assertEqual(r['direction'], 'SELL')
            self.assertEqual(r['source_position_limit'], count)
            self.assertGreater(r['stop_loss'], 4000.)

    def test_ties_wait_and_majority_wins(self):
        r = self.vote([('BUY', 90, True), ('SELL', 90, True), ('WAIT', 0, True)])
        self.assertFalse(r['allowed'])
        r = self.vote([('BUY', 90, True), ('SELL', 90, True), ('SELL', 80, True)])
        self.assertEqual(r['direction'], 'SELL')
        self.assertEqual(r['source_position_limit'], 2)

    def test_unusable_and_weak_sources_never_count(self):
        r = self.vote([('BUY', 99, False), ('BUY', 74, True), ('WAIT', 99, True)])
        self.assertFalse(r['allowed'])
        self.assertEqual(r['source_position_limit'], 0)

    def test_news_remains_a_veto(self):
        r = self.vote([('BUY', 90, True)]*3, news_block=True)
        self.assertFalse(r['allowed'])

    def test_broker_additions_require_profit_and_respect_vote_allowance(self):
        from services.research.gold_scalp_additions import addition_blocks
        position = dict(direction='BUY', sl=3998., entry_price=4000.2, volume=.01, profit=-.2)
        decision = dict(direction='BUY', entry_mode='THREE_SOURCE_VOTE', source_position_limit=2)
        self.assertTrue(addition_blocks(decision, [position], 4000., 4000.2))
        position.update(entry_price=3999.,profit=1.)
        self.assertEqual(addition_blocks(decision, [position], 4000., 4000.2), [])
        self.assertTrue(addition_blocks(decision, [position, position], 4000., 4000.2))
        bad = dict(position, sl=0)
        self.assertTrue(addition_blocks(decision, [bad], 4000., 4000.2))

    def test_duplicate_or_expired_source_cannot_increase_allocation(self):
        c = dict(advisor='MT5_CANDLES', bias='BUY', evidence=90, source_usable=True)
        r = source_vote(dict(contributors=[c, c]),
            dict(available=True, bid=4000., ask=4000.2, atr=2.), now=1000.)
        self.assertEqual(r['source_position_limit'], 1)
        c['valid_until'] = '1970-01-01T00:00:00+00:00'
        r = source_vote(dict(contributors=[c]),
            dict(available=True, bid=4000., ask=4000.2, atr=2.), now=1000.)
        self.assertFalse(r['allowed'])

    def test_two_candle_feeds_are_one_analysis_family(self):
        r=self.vote([('BUY',90,True),('BUY',95,True),('WAIT',0,True)])
        self.assertEqual(r['source_position_limit'],2)
        self.assertEqual(r['support_family_count'],1)
        r=self.vote([('BUY',90,True)]*3)
        self.assertEqual(r['support_family_count'],2)


if __name__ == '__main__':
    unittest.main()
