import unittest

from services.research.gold_retest_shadow import retest_observation


class RetestShadowTests(unittest.TestCase):
    def bars(self):
        rows = [dict(time=index*60, open=99, close=99.2, high=100, low=98)
                for index in range(20)]
        rows.append(dict(time=1200, open=99.5, close=101, high=101.5, low=99))
        rows.append(dict(time=1260, open=100.3, close=100.8, high=101, low=100.05))
        return rows

    def observe(self, bars, **changes):
        inputs = dict(now=bars[-1]['time']+60, direction='BUY', atr=2, offset=0)
        inputs.update(changes)
        return retest_observation(bars, **inputs)

    def test_retest_requires_a_later_closed_bar(self):
        result = self.observe(self.bars())
        self.assertEqual(result['state'], 'CONFIRMED_NOW')
        self.assertEqual(result['level'], 100)
        self.assertFalse(result['execution_enabled'])
        self.assertFalse(self.observe(self.bars()[:-1])['available'])

    def test_sell_geometry_is_symmetric(self):
        rows = [dict(time=bar['time'], open=200-bar['open'], close=200-bar['close'],
                     high=200-bar['low'], low=200-bar['high']) for bar in self.bars()]
        self.assertEqual(self.observe(rows, direction='SELL')['state'], 'CONFIRMED_NOW')

    def test_forming_candle_cannot_confirm_or_invalidate(self):
        rows = self.bars()
        result = self.observe(rows)
        rows.append(dict(time=1320, open=90, close=89, low=88, high=91))
        self.assertEqual(self.observe(rows, now=1320), result)

    def test_failed_retest_invalidates(self):
        rows = self.bars()
        rows[-1].update(open=100.3, close=99.8, low=99.5)
        self.assertEqual(self.observe(rows)['state'], 'INVALIDATED')

    def test_wait_then_expiry_without_a_touch(self):
        rows = self.bars()
        rows[-1].update(open=101, close=101.1, high=101.5, low=100.5)
        self.assertEqual(self.observe(rows)['state'], 'WAIT_RETEST')
        for index in range(3):
            rows.append(dict(time=1320+index*60, open=101, close=101.1, high=101.5, low=100.5))
        self.assertEqual(self.observe(rows)['state'], 'EXPIRED')

    def test_confirmation_is_not_repeated_on_next_bar(self):
        rows = self.bars()
        rows.append(dict(time=1320, open=101, close=101.1, high=101.5, low=100.5))
        self.assertEqual(self.observe(rows)['state'], 'ALREADY_CONFIRMED')

    def test_later_context_atr_does_not_rewrite_retest_tolerance(self):
        initial = self.observe(self.bars(), atr=2)
        self.assertEqual(initial, self.observe(self.bars(), atr=200))

    def test_invalid_data_fail_without_execution_authority(self):
        rows = self.bars()
        for changes in (dict(atr=0), dict(atr=float('nan')), dict(lookback=True),
                        dict(expiry_bars=11), dict(now=1380)):
            self.assertFalse(self.observe(rows, **changes)['available'])
        self.assertFalse(self.observe(rows[1:10]+rows[11:])['available'])
        self.assertFalse(self.observe(rows+rows[-1:])['available'])
