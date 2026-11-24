import unittest
from unittest.mock import patch
from config import gold_consensus_settings as settings
from services.research.gold_micro_flow import MicroFlow, fast_profit_take
from services.research.gold_scalp_guard import reconcile, reentry_blocks
from services.research.gold_position_conscience import assess_position_conscience
from services.research.gold_horizon_policy import flow_primary_levels, build_horizon_decisions
from services.research.gold_adaptive_exit import evaluate_adaptive_exit
from run_gold_consensus_bot import _scalp_churn_blocks, _lane_risk_usd
from test_gold_horizon_policy import _consensus


class MicroFlowTests(unittest.TestCase):
    def stream(self, sign=1, spread_only=False):
        engine=MicroFlow()
        for t in range(0,42,2):
            bid=2000+sign*t*.08
            ask=2000.2 if spread_only else bid+.2
            engine.observe(quote_time=t, bid=bid, ask=ask, now=t)
        return engine

    def test_windows_observable_at_loop_cadence(self):
        flow=self.stream().read('BUY',now=40)
        self.assertTrue(flow['available'])
        self.assertEqual(len(flow['windows']),3)
        self.assertEqual(flow['bias'],'BUY')
        self.assertEqual(flow['reversal_risk'],0)

    def test_opposing_flow_has_high_risk_both_sides(self):
        for sign,held in [(1,'SELL'),(-1,'BUY')]:
            self.assertGreater(self.stream(sign).read(held,now=40)['reversal_risk'],.7)

    def test_spread_alone_does_not_create_direction(self):
        flow=self.stream(-1,True).read('BUY',now=40)
        self.assertEqual(flow['reversal_risk'],0)
        self.assertEqual(flow['bias'],'NEUTRAL')

    def test_stale_future_gap_and_repeated_observations(self):
        engine=self.stream()
        self.assertFalse(engine.read('BUY',now=44)['available'])
        count=len(engine.samples)
        for t in (40,39):
            self.assertFalse(engine.observe(quote_time=t,bid=2000,ask=2000.2,now=40))
        self.assertEqual(len(engine.samples),count)
        engine.observe(quote_time=42,bid=2000,ask=2000.2,now=40)
        self.assertTrue(engine.read(now=40)['available'])  # bounded broker clock jitter
        engine.observe(quote_time=46,bid=2000,ask=2000.2,now=40)
        self.assertFalse(engine.read(now=40)['available'])
        engine=self.stream()
        engine.observe(quote_time=60,bid=2000,ask=2000.2,now=60)
        self.assertEqual(len(engine.samples),1)
        self.assertFalse(engine.read(now=60)['available'])

    def test_dense_short_burst_is_not_three_independent_windows(self):
        engine=MicroFlow()
        for n in range(100): engine.observe(quote_time=n/100,bid=2000+n/100,ask=2000.2+n/100,now=n/100)
        self.assertFalse(engine.read(now=1)['available'])

    def test_cost_floor_and_nonfinite_risk(self):
        for move,risk,expected in [(.2,.9,False),(1,.2,False),(1,.9,True),(1,float('nan'),False)]:
            self.assertEqual(fast_profit_take(dict(available=True,reversal_risk=risk),move=move,spread=.2)[0],expected)

    def test_quiet_is_neutral_not_full_support(self):
        result=assess_position_conscience(direction='BUY',horizon='SCALP',
            micro_flow=dict(available=True,pressure=0,reversal_risk=0))
        self.assertEqual(result['conviction'],.5)

    def test_smoothing_falls_immediately_and_recovers_slowly(self):
        state={}
        def assess(pressure,t):
            return assess_position_conscience(direction='BUY',horizon='SCALP',state=state,now=t,
                micro_flow=dict(available=True,pressure=pressure))['alignment']
        self.assertEqual(assess(1,0),1)
        self.assertEqual(assess(-1,2),-1)
        self.assertLess(assess(1,4),0)


class ContinuousGuardTests(unittest.TestCase):
    def history(self):
        return [dict(ticket=i,direction='BUY',opened_epoch=i*20,closed_epoch=i*20+10,profit=-.2)
                for i in range(1,5)]

    def test_reconcile_net_losses_idempotent_and_survives_restart(self):
        state={}
        for _ in range(3): reconcile(state,self.history(),[],now=100)
        self.assertEqual(state['consecutive_losses'],4)
        self.assertEqual(len(state['entry_times']),4)
        self.assertTrue(_scalp_churn_blocks(state,now=100,spread=.2,context={}))
        self.assertFalse(_scalp_churn_blocks(state,now=1000,spread=.2,context={}))
        restarted={};reconcile(restarted,self.history(),[],now=100)
        self.assertEqual(restarted['consecutive_losses'],4)

    def test_pending_close_blocks_until_realized_history_arrives(self):
        state={'pending_closed':['4']}
        reconcile(state,[],[],now=100)
        self.assertTrue(reentry_blocks(state,now=100,direction='SELL'))
        reconcile(state,self.history(),[],now=100)
        self.assertEqual(state['pending_closed'],[])
        self.assertTrue(reentry_blocks(state,now=100,direction='SELL'))
        self.assertTrue(reentry_blocks(state,now=119,direction='SELL'))
        self.assertFalse(reentry_blocks(state,now=120,direction='SELL'))

    def test_missing_history_fails_closed(self):
        state={};reconcile(state,None,[],now=100)
        self.assertTrue(reentry_blocks(state,now=100,direction='BUY'))

    def test_rate_spread_and_expansion_guards(self):
        self.assertTrue(_scalp_churn_blocks({'entry_times':[99]*30},now=100,spread=.2,context={}))
        for spread in (settings.SCALP_MAX_SPREAD_USD+.01,float('nan'),float('inf'),-.1):
            self.assertTrue(_scalp_churn_blocks({},now=100,spread=spread,context={}))
        self.assertTrue(_scalp_churn_blocks({},now=100,spread=.2,
            context={'structure_research':{'regime':'VOLATILITY_EXPANSION'}}))

    def test_risk_unit_never_exceeds_per_trade_cap(self):
        self.assertEqual(_lane_risk_usd(settings.HORIZON_LANES['SCALP']),5.)
        self.assertEqual(_lane_risk_usd(dict(stop_mode='INDIVIDUAL', individual_stop_loss_usd=500)),5.)

    def test_actual_stop_anchors_r_and_zero_conviction_does_not_protect_hold(self):
        position=dict(ticket=1,direction='BUY',entry_price=2000.,volume=.01,sl=1999.)
        context=dict(available=True,atr=1.,momentum=1,trend=1,close=2000.,previous_low=1990,previous_high=2010)
        state={}
        def run(bid):
            return evaluate_adaptive_exit({},[position],context,state,now=100,bid=bid,ask=bid+.1,
                feed_age=0,config=settings.ADAPTIVE_EXIT_CONFIG['SCALP'],risk_usd=2.,
                conscience=dict(available=True,conviction=0,alignment=-1))
        self.assertEqual(run(2000.5)['risk_price'],1.)
        position['sl']=1999.9
        result=run(2000.1)
        self.assertEqual(result['risk_price'],1.)
        self.assertTrue(result['close'])


@patch.dict(settings.HORIZON_LANES['SCALP'], {'entry_mode': 'FLOW_PRIMARY'})
@patch('config.gold_consensus_settings.CONTINUOUS_DIRECTIONAL_ENTRIES', False)
class FlowPrimaryPolicyTests(unittest.TestCase):
    def test_levels_both_sides_and_invalid_volatility(self):
        for direction in ('BUY','SELL'):
            levels=flow_primary_levels(direction,2000,2)
            self.assertEqual(levels['entry_reference'],2000)
            self.assertEqual(levels['tp1']>2000,direction=='BUY')
            self.assertEqual(levels['sl']<2000,direction=='BUY')
        for atr in (0,-1,float('nan'),float('inf')):
            self.assertEqual(flow_primary_levels('BUY',2000,atr),{})

    def test_missing_context_unusable_flow_and_nan_cannot_authorize(self):
        context={'SCALP':dict(available=True,atr=2,bid=2000,ask=2000.2)}
        consensus=_consensus(('WAIT',0),('WAIT',0),('BUY',90))
        self.assertFalse(build_horizon_decisions(consensus)['SCALP']['allowed'])
        for horizon in consensus['horizons'].values():
            horizon['advisors']['MT5_TICK_FLOW']['evidence']=float('nan')
        self.assertFalse(build_horizon_decisions(consensus,market_context=context)['SCALP']['allowed'])

    def test_buy_uses_ask_sell_uses_bid_and_threshold_matches_flow(self):
        context={'SCALP':dict(available=True,atr=2,bid=2000,ask=2000.2,close=1980)}
        for direction in ('BUY','SELL'):
            result=build_horizon_decisions(_consensus(('WAIT',0),('WAIT',0),(direction,65)),market_context=context)['SCALP']
            self.assertTrue(result['allowed'])
            self.assertEqual(result['entry_reference'],2000.2 if direction=='BUY' else 2000)
            self.assertEqual(result['entry_threshold'],60.)


class ForecastIntegrityTests(unittest.TestCase):
    def test_m1_management_bar_cannot_repeat_m5_forecast_confirmation(self):
        import pandas as pd
        from types import SimpleNamespace
        from unittest.mock import Mock
        from services.research.gold_learned_policy import GoldLearnedPolicy
        policy=GoldLearnedPolicy.__new__(GoldLearnedPolicy)
        predictor=Mock();predictor.predict.return_value=[.1]
        policy.models={'SCALP':dict(model=predictor,training_last_bar=0,round_trip_slippage_usd=.1,
            model_id='test',forecast_bars=3,minimum_edge_usd=.2,validation={})}
        policy.cache={}
        times=pd.date_range(end='2026-09-15T12:00:00Z',periods=65,freq='5min')
        bars=pd.DataFrame(dict(time=times,open=2000.,high=2001.,low=1999.,close=[2000+i*.01 for i in range(65)]))
        snapshot=SimpleNamespace(candles={'M5':bars},timestamp=pd.Timestamp('2026-09-15T12:05:00Z'),bid=2000,ask=2000.2)
        first=policy.assess(snapshot,'SCALP',dict(available=True,bar_id='m1-first'))
        snapshot.timestamp+=pd.Timedelta(minutes=1)
        second=policy.assess(snapshot,'SCALP',dict(available=True,bar_id='m1-next'))
        self.assertEqual(first['bar_id'],second['bar_id'])
        predictor.predict.assert_called_once()

    def test_training_labels_never_reach_test_period(self):
        import numpy as np
        from tools.audit_continuous_scalp import chronological_split
        times=np.arange(100.)
        train,test,boundary=chronological_split(times,times+30)
        self.assertLess((times[train]+30).max(),times[test].min())

    def test_restarted_open_position_counts_toward_rate_limit(self):
        state={}
        reconcile(state,[],[dict(ticket=3,opened_epoch=50)],now=100)
        self.assertEqual(state['entry_times'],[50])
