import unittest

from tools.validate_gold_fast import calibrate, m1_direction, screen


class FastValidationTests(unittest.TestCase):
    def pair(self):
        deals = [dict(symbol='XAUUSD', magic=631011, position_id=10, ticket=1, entry=0,
                      type=0, volume=.01, price=4000., profit=0., commission=-.02, fee=0., swap=0.),
                 dict(symbol='XAUUSD', magic=631011, position_id=10, ticket=2, entry=1,
                      type=1, volume=.01, price=4001., profit=1., commission=-.02, fee=0., swap=0.)]
        journal = [dict(success=True, record_type='HORIZON_OPEN', deal=1, entry_price=3999.9,
                        execution_metrics=dict(order_send_elapsed_ms=100)),
                   dict(success=True, record_type='CLOSE', deal=2, requested_price=4001.2,
                        execution_metrics=dict(order_send_elapsed_ms=200))]
        return deals, journal

    def test_confirmed_costs_use_deal_side(self):
        deals, journal = self.pair()
        result = calibrate(deals, journal, 100., minimum=1)
        self.assertTrue(result['available'])
        self.assertAlmostEqual(result['commission_price'], .04)
        self.assertAlmostEqual(result['slippage_price'], .3)

    def test_default_sample_minimum_does_not_assume_zero(self):
        deals, journal = self.pair()
        result = calibrate(deals, journal, 100.)
        self.assertFalse(result['available'])
        self.assertIsNone(result['commission_price'])
        self.assertIsNone(result['slippage_price'])

    def test_unbound_or_partial_fills_are_not_cost_evidence(self):
        deals, journal = self.pair()
        self.assertEqual(calibrate(deals, journal[:1], 100., minimum=1)['reconciled_pairs'], 0)
        self.assertEqual(calibrate(deals+[dict(deals[1], ticket=3)], journal, 100., minimum=1)['reconciled_pairs'], 0)

    def test_contract_reconciliation_rejects_wrong_conversion(self):
        deals, journal = self.pair()
        self.assertFalse(calibrate(deals, journal, 1000., minimum=1)['available'])

    def test_no_costs_no_net_validation(self):
        result = screen([], dict(available=False, reason='unknown'))
        self.assertFalse(result['available'])
        self.assertFalse(result['execution_enabled'])

    def test_m1_excludes_forming_bar_and_rejects_gaps(self):
        ticks = [dict(timestamp=stamp, bid=4000+stamp*.1, ask=4000.02+stamp*.1)
                 for stamp in range(240)]
        self.assertEqual(m1_direction(ticks, 239)[0], 'BUY')
        self.assertEqual(m1_direction([tick for tick in ticks if not 20 < tick['timestamp'] < 40], 239)[0], 'WAIT')

    def test_screen_is_deduplicated_and_always_non_executing(self):
        ticks = [dict(timestamp=stamp, bid=4000+stamp*.1, ask=4000.02+stamp*.1)
                 for stamp in range(600)]
        result = screen(ticks, dict(available=True, commission_price=.01, slippage_price=.02))
        self.assertFalse(result['execution_enabled'])
        self.assertGreater(result['summary']['S30']['candidates'], 0)
        for records in result['observations'].values():
            self.assertEqual(len(records), len({row['setup_id'] for row in records}))
            self.assertTrue(all(row['entry_epoch'] > row['decision_epoch'] for row in records))


if __name__ == '__main__':
    unittest.main()
