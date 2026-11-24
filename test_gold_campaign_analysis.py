import unittest
from tools.analyze_scalp_campaigns import campaign_summary, epoch


class CampaignAnalysisTests(unittest.TestCase):
    def trade(self, ticket, start, end, profit):
        return dict(position_id=ticket, opened_at=f'2026-10-19T00:{start}:00Z',
                    closed_at=f'2026-10-19T00:{end}:00Z', profit=profit)

    def test_overlapping_additions_form_one_campaign(self):
        result = campaign_summary([self.trade(1, '00', '05', 2), self.trade(2, '02', '06', -1)])
        self.assertEqual(result['settled_campaigns']['trades'], 1)
        self.assertEqual(result['settled_campaigns']['net'], 1)
        self.assertEqual(result['additional_cost_stress']['0.5']['net'], 0)

    def test_touching_intervals_are_separate(self):
        result = campaign_summary([self.trade(1, '00', '05', 2), self.trade(2, '05', '06', -1)])
        self.assertEqual(result['settled_campaigns']['trades'], 2)

    def test_open_campaign_is_not_reported_as_a_completed_winner(self):
        result = campaign_summary([self.trade(1, '00', '05', 2)],
                                  [dict(ticket=2, opened_epoch=epoch('2026-10-19T00:02:00Z'))])
        self.assertEqual(result['settled_campaigns']['trades'], 0)
        self.assertEqual(result['incomplete_campaigns'][0]['tickets'], [1, 2])

    def test_invalid_time_and_profit_fail_explicitly(self):
        with self.assertRaises(ValueError):
            epoch('2026-10-19T00:00:00')
        with self.assertRaises(ValueError):
            campaign_summary([self.trade(1, '05', '00', 1)])
        with self.assertRaises(ValueError):
            campaign_summary([self.trade(1, '00', '05', float('nan'))])
        with self.assertRaises(ValueError):
            campaign_summary([self.trade(1, '00', '05', 1)]*2)
