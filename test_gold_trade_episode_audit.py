import unittest
from services.research.gold_trade_episode_audit import episode_audit


class TradeEpisodeAuditTests(unittest.TestCase):
    def test_overlapping_additions_are_one_episode(self):
        trades = [dict(opened_at='2026-10-09T05:00:00+00:00',closed_at='2026-10-09T05:05:00+00:00',profit=1),
                  dict(opened_at='2026-10-09T05:02:00+00:00',closed_at='2026-10-09T05:06:00+00:00',profit=2),
                  dict(opened_at='2026-10-09T05:06:30+00:00',closed_at='2026-10-09T05:07:00+00:00',profit=-1),
                  dict(opened_at='2026-10-09T05:08:00+00:00',closed_at='2026-10-09T05:09:00+00:00',profit=-3)]
        result = episode_audit(list(reversed(trades)))
        self.assertEqual(result['episodes'],2)
        self.assertEqual(result['clusters'][0]['trades'],3)
        self.assertEqual(result['total_closed_profit'],-1)
        self.assertEqual(result,episode_audit(trades))
