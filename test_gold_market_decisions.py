import unittest
import pandas as pd
from tools.audit_gold_market_decisions import Quotes,pre_entry_features,evaluate,completed_context


class MarketDecisionTests(unittest.TestCase):
    def ticks(self):
        return pd.DataFrame([dict(timestamp=i*.5,bid=4000+i*.01,ask=4000.2+i*.01) for i in range(161)])

    def test_future_quotes_cannot_change_preentry_features(self):
        ticks=self.ticks()
        a=pre_entry_features(Quotes(ticks),40.,'BUY',entry_price=4001.,stop_distance=1.)
        future=ticks.copy();future.loc[future.timestamp>40,['bid','ask']]+=100
        b=pre_entry_features(Quotes(future),40.,'BUY',entry_price=4001.,stop_distance=1.)
        self.assertEqual(a,b)

    def test_preentry_features_match_prefix_snapshot_without_any_future_rows(self):
        ticks=self.ticks()
        original=pre_entry_features(Quotes(ticks),40.25,'BUY',entry_price=4001.,stop_distance=1.)
        prefix=pre_entry_features(Quotes(ticks[ticks.timestamp<=40.25]),40.25,'BUY',entry_price=4001.,stop_distance=1.)
        self.assertEqual(original,prefix)

    def test_signed_pressure_and_executable_excursions_use_bid_for_buy_ask_for_sell(self):
        ticks=self.ticks()
        trades=[]
        for i,direction in enumerate(('BUY','SELL')):
            trades.append(dict(position_id=i+1,opened_utc='1970-01-01T00:00:40+00:00',
                closed_utc='1970-01-01T00:00:50+00:00',direction=direction,entry_price=4001.,
                volume=.01,net=-.5,initial_stop_distance=1.))
        rows=evaluate(dict(closed_positions=trades),ticks)['positions']
        self.assertGreater(rows[0]['pre_entry']['pressure']['12']['signed_bid_move_price'],0)
        self.assertLess(rows[1]['pre_entry']['pressure']['12']['signed_bid_move_price'],0)
        self.assertAlmostEqual(rows[0]['during']['maximum_favorable_gross_usd'],0.)
        self.assertAlmostEqual(rows[1]['during']['maximum_favorable_gross_usd'],0.)
        self.assertAlmostEqual(rows[0]['during']['maximum_adverse_gross_usd'],-.2)
        self.assertAlmostEqual(rows[1]['during']['maximum_adverse_gross_usd'],-.2)

    def test_missing_capture_is_explicit_not_interpolated(self):
        trade=dict(position_id=1,opened_utc='1970-01-01T00:05:40+00:00',
            closed_utc='1970-01-01T00:05:50+00:00',direction='BUY',entry_price=4001.,
            volume=.01,net=-.5,initial_stop_distance=1.)
        row=evaluate(dict(closed_positions=[trade]),self.ticks())['positions'][0]
        self.assertFalse(row['during']['available'])
        self.assertIn('TRADE_PATH_UNASSESSABLE_FROM_CAPTURE',row['flags'])
        self.assertNotIn('maximum_favorable_gross_usd',row['during'])

    def test_candle_context_excludes_forming_bar(self):
        bars=pd.DataFrame([dict(time=i*60.,open=4000+i,high=4002+i,low=3999+i,close=4001+i) for i in range(20)])
        before=completed_context(bars,60,1000.,1)
        future=bars.copy();future.loc[future.time+60>1000.,['open','high','low','close']]+=1000
        self.assertEqual(before,completed_context(future,60,1000.,1))
        self.assertLessEqual(before['last_completed_close_epoch'],1000.)


if __name__=='__main__':
    unittest.main()
