import unittest
from types import SimpleNamespace
import pandas as pd

from services.research.gold_adaptive_exit import market_exit_context, evaluate_adaptive_exit


class AdaptiveExitTests(unittest.TestCase):
    def setUp(self):
        self.context=dict(available=True,atr=2.,trend=1.,momentum=1.,close=105.,previous_low=100.,previous_high=110.)
        self.positions=[dict(ticket=1,direction='BUY',volume=.01,entry_price=100)]
        self.decision=dict(allowed=True,direction='BUY')
        self.state={}

    def evaluate(self,now=0,bid=105,ask=105.2,feed_age=0,config=None,risk_usd=4.,conscience=None):
        return evaluate_adaptive_exit(self.decision,self.positions,self.context,self.state,
            now=now,bid=bid,ask=ask,feed_age=feed_age,config=config or {},risk_usd=risk_usd,
            contract_size=100.,conscience=conscience)

    def test_no_fixed_five_dollar_profit_exit(self):
        self.assertFalse(self.evaluate(bid=103,ask=103.2)['close'])

    def test_twenty_percent_profit_giveback_selects_only_armed_ticket(self):
        cfg = dict(profit_lock_arm_usd=6., profit_lock_retained_fraction=.8)
        supported = dict(available=True, conviction=.85, alignment=.7, coverage=1.)
        self.assertFalse(self.evaluate(bid=106, ask=106.2, config=cfg, conscience=supported)['close'])
        # Adding another position must not erase the first position's high-water mark.
        self.positions.append(dict(ticket=2, direction='BUY', volume=.01, entry_price=105))
        self.assertFalse(self.evaluate(bid=105, ask=105.2, config=cfg, conscience=supported)['close'])
        result = self.evaluate(bid=104.8, ask=105, config=cfg, conscience=supported)
        self.assertTrue(result['close'])
        self.assertEqual(result['close_tickets'], [1])

    def test_sell_profit_lock_tracks_higher_peak_and_rejects_stale_quote(self):
        cfg = dict(profit_lock_arm_usd=6., profit_lock_retained_fraction=.8)
        self.positions[0]['direction'] = 'SELL'
        supported = dict(available=True, conviction=.85, alignment=.7, coverage=1.)
        self.evaluate(bid=89.8, ask=90, config=cfg, conscience=supported)
        self.assertFalse(self.evaluate(bid=91.8, ask=92, feed_age=1000, config=cfg)['close'])
        result = self.evaluate(bid=91.8, ask=92, config=cfg, conscience=supported)
        self.assertEqual(result['close_tickets'], [1])

    def test_trailing_holds_only_while_the_conscience_supports_the_trade(self):
        """Giveback protects by default; a supported, non-weakening trade runs.

        Without conviction evidence the giveback is enforced: an unsupported
        winner is banked rather than ridden back to the stop.
        """
        supported=dict(available=True,conviction=.85,alignment=.7,coverage=1.)
        self.evaluate(bid=110,ask=110.2,conscience=supported)
        self.assertFalse(self.evaluate(now=10,bid=106,ask=106.2,conscience=supported)['close'])
        self.state.clear()
        self.evaluate(bid=110,ask=110.2)
        self.assertTrue(self.evaluate(now=10,bid=106,ask=106.2)['close'])

    def test_trailing_fires_on_weakening_and_handles_both_sides(self):
        self.evaluate(bid=110,ask=110.2)
        self.context['momentum']=-1
        self.assertTrue(self.evaluate(now=20,bid=106,ask=106.2)['close'])
        self.positions[0]['direction']='SELL';self.positions[0]['ticket']=2
        self.context.update(trend=-1,momentum=-1)
        self.evaluate(now=30,bid=89.8,ask=90)
        self.context['momentum']=1
        self.assertTrue(self.evaluate(now=40,bid=93.8,ask=94)['close'])

    def test_reversal_must_be_authorized_and_persist(self):
        self.decision.update(allowed=False,direction='SELL')
        self.assertFalse(self.evaluate()['close'])
        self.decision['allowed']=True
        self.assertFalse(self.evaluate(now=1)['close'])
        self.assertTrue(self.evaluate(now=17)['close'])

    def test_stale_feed_does_not_invent_reversal(self):
        self.decision.update(direction='SELL')
        self.assertFalse(self.evaluate(feed_age=30)['close'])
        self.decision.update(news_block=True,news_policy='CLOSE_AND_BLOCK')
        self.assertTrue(self.evaluate(feed_age=30)['close'])

    def test_quiet_feed_still_manages_the_position(self):
        """Seconds without a new tick must not disarm protection."""
        self.evaluate(bid=110,ask=110.2,feed_age=6)
        self.context['momentum']=-1
        result=self.evaluate(now=20,bid=106,ask=106.2,feed_age=6)
        self.assertTrue(result['close'])

    def test_peak_does_not_transfer_to_new_trade(self):
        self.evaluate(bid=110,ask=110.2)
        self.positions[0]['ticket']=2;self.context['momentum']=-1
        self.assertFalse(self.evaluate(now=20,bid=101,ask=101.2)['close'])

    def test_forming_candle_is_excluded(self):
        now=pd.Timestamp('2026-01-01T12:00:30Z')
        times=pd.date_range(end='2026-01-01T12:00:00Z',periods=60,freq='1min')
        bars=pd.DataFrame(dict(time=times,open=100.,high=102.,low=99.,close=101.))
        snapshot=SimpleNamespace(candles={'M1':bars},timestamp=now)
        before=market_exit_context(snapshot,'SCALP')
        bars.loc[59,['open','high','low','close']]=[10000,10001,9999,10000]
        self.assertEqual(before,market_exit_context(snapshot,'SCALP'))
        self.assertTrue(before['available'])

    def test_stale_candles_unavailable(self):
        bars=pd.DataFrame(dict(time=pd.date_range('2026-01-01',periods=60,freq='1min',tz='UTC'),
                               open=100.,high=102.,low=99.,close=101.))
        result=market_exit_context(SimpleNamespace(candles={'M1':bars},timestamp=pd.Timestamp('2026-01-03T12:00:00Z')),'SCALP')
        self.assertFalse(result['available'])


if __name__=='__main__':unittest.main()
