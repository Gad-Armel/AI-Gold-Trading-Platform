"""Trade accounting in the read-only forward review must not invent outcomes."""
import unittest
from tools.summarize_scalper_observations import summarize


def deal(ticket,entry,volume,net,time='2026.10.01 10:00:00',owned=True):
    return dict(ticket=str(ticket),position='100',entry=entry,volume=volume,net=net,
                time=time,owned=owned,comment='ScalperExpert321:S1',side='BUY',reason='DEAL_REASON_EXPERT')


def row(deals,second=0):
    return {'observed_utc':f'2026-10-01T07:00:{second:02d}+00:00','state':'live',
            'snapshot':{'deals':deals,'candles':[],'status':'TEST','market':{'spread':.3}}}


class ObservationReviewTests(unittest.TestCase):
    def test_partial_close_does_not_count_as_winner(self):
        result=summarize([row([deal(1,'DEAL_ENTRY_IN',.01,-.04),deal(2,'DEAL_ENTRY_OUT',.005,.1)])])
        self.assertEqual(result['trades'],[])

    def test_repeated_snapshots_do_not_duplicate_fills(self):
        fills=[deal(1,'DEAL_ENTRY_IN',.01,-.04),deal(2,'DEAL_ENTRY_OUT',.01,.2)]
        result=summarize([row(fills),row(fills,35)])
        self.assertEqual(result['cohorts']['ScalperExpert321']['closed'],1)
        self.assertEqual(result['cohorts']['ScalperExpert321']['net'],.16)
        self.assertEqual(result['cadence_median_seconds'],35)

    def test_entry_retained_when_rolling_feed_only_has_exit(self):
        result=summarize([row([deal(1,'DEAL_ENTRY_IN',.01,-.04)]),row([deal(2,'DEAL_ENTRY_OUT',.01,-.6)],35)])
        self.assertEqual(result['cohorts']['ScalperExpert321']['net'],-.64)

    def test_manual_entry_is_not_attributed_to_ea(self):
        result=summarize([row([deal(1,'DEAL_ENTRY_IN',.01,0,owned=False),deal(2,'DEAL_ENTRY_OUT',.01,20,owned=False)])])
        self.assertEqual(result['cohorts'],{})

    def test_partial_exit_order_uses_last_broker_fill(self):
        last=deal(3,'DEAL_ENTRY_OUT',.005,.2,'2026.10.01 10:02:00');last['reason']='DEAL_REASON_SL'
        result=summarize([row([last,deal(2,'DEAL_ENTRY_OUT',.005,.1,'2026.10.01 10:01:00'),deal(1,'DEAL_ENTRY_IN',.01,0)])])
        self.assertEqual(result['trades'][0]['exit_reason'],'DEAL_REASON_SL')
        self.assertEqual(result['trades'][0]['net'],.3)


if __name__=='__main__':
    unittest.main()
