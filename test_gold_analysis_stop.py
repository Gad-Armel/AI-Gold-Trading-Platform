import tempfile
import unittest
from unittest.mock import patch
from config import gold_consensus_settings as settings
from services.execution.gold_consensus_demo_broker import open_horizon_position
from services.execution.gold_paper_portfolio import GoldPaperPortfolio
from test_gold_consensus_demo_broker import FakeMT5
from run_gold_consensus_bot import _lane_risk_usd


class AnalysisStopTests(unittest.TestCase):
    def setUp(self):
        for item in [patch('services.execution.gold_consensus_demo_broker._journal'),
                     patch('services.execution.gold_consensus_demo_broker.validate_demo_session_identity',return_value=(True,'')),
                     patch('config.gold_consensus_settings.MT5_SERVER_UTC_OFFSET_SECONDS',0),
                     patch.dict(settings.HORIZON_LANES['SCALP'],stop_mode='ANALYSIS',individual_stop_loss_usd=None)]:
            item.start(); self.addCleanup(item.stop)

    def test_structural_stop_keeps_more_than_five_dollars_without_fixed_cap(self):
        for side,target,stop in [('BUY',4010,3990),('SELL',3990,4010)]:
            mt5=FakeMT5()
            result=open_horizon_position(mt5,'SCALP',dict(allowed=True,direction=side,take_profit=target,stop_loss=stop))
            self.assertTrue(result['success'],result)
            self.assertEqual(mt5.sent[0]['sl'],stop)

    def test_analysis_still_rejects_unvalued_or_invalid_broker_stops(self):
        mt5=FakeMT5(); mt5.order_calc_profit=lambda *a:None
        self.assertFalse(open_horizon_position(mt5,'SCALP',dict(allowed=True,direction='BUY',take_profit=4010,stop_loss=3990))['success'])
        mt5=FakeMT5(); mt5.info.trade_tick_size=.5
        self.assertEqual(open_horizon_position(mt5,'SCALP',dict(allowed=True,direction='BUY',take_profit=4010,stop_loss=3990.1))['action'],'STOP_GRID_BLOCK')

    def test_risk_reference_uses_total_actual_stop_exposure(self):
        positions=[dict(entry_price=100.,sl=92.,volume=.01),dict(entry_price=101.,sl=92.,volume=.01)]
        self.assertEqual(_lane_risk_usd(settings.HORIZON_LANES['SCALP'],positions,100),17.)
        self.assertEqual(_lane_risk_usd(settings.HORIZON_LANES['SCALP']),5.)

    def test_s30_stop_rounds_inward_to_actual_broker_tick_grid(self):
        for side, target, raw, expected in [('BUY', 4010, 3990.123, 3990.5),
                                            ('SELL', 3990, 4010.123, 4010.)]:
            mt5 = FakeMT5()
            mt5.info.trade_tick_size = .5
            mt5.info.digits = 2
            result = open_horizon_position(mt5, 'SCALP', dict(allowed=True, direction=side,
                take_profit=target, stop_loss=raw, entry_mode='S30_PRIMARY'))
            self.assertTrue(result['success'], result)
            self.assertEqual(mt5.sent[0]['sl'], expected)

    def test_s30_grid_alignment_does_not_bypass_stop_distance(self):
        mt5 = FakeMT5()
        mt5.info.trade_tick_size = .01
        mt5.info.trade_stops_level = 100
        result = open_horizon_position(mt5, 'SCALP', dict(allowed=True, direction='BUY',
            take_profit=4010, stop_loss=3999.556, entry_mode='S30_PRIMARY'))
        self.assertEqual(result['action'], 'STOP_GRID_BLOCK')
        self.assertEqual(mt5.sent, [])

    def test_s5_also_aligns_stop_without_removing_it(self):
        mt5 = FakeMT5()
        mt5.info.trade_tick_size = .01
        result = open_horizon_position(mt5, 'SCALP', dict(allowed=True, direction='BUY',
            take_profit=4010, stop_loss=3998.123, entry_mode='S5_PRIMARY'))
        self.assertTrue(result['success'], result)
        self.assertEqual(mt5.sent[0]['sl'], 3998.13)
        self.assertEqual(mt5.sent[0]['tp'], 0.)

    def test_paper_analysis_stop_matches_requested_price_without_five_dollar_cap(self):
        with tempfile.TemporaryDirectory() as folder:
            p=GoldPaperPortfolio(folder);p.mark(4000,4000.2,1000,0)
            result=p.open('SCALP',dict(allowed=True,direction='BUY',take_profit=4010,stop_loss=3990),margin=10,stop_mode='ANALYSIS')
            self.assertTrue(result['success'],result)
            self.assertEqual(p.positions[0]['sl'],3990)
            self.assertGreater(p.positions[0]['entry_price']-p.positions[0]['sl'],5)


if __name__=='__main__':
    unittest.main()
