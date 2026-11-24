import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from services.research.gold_entry_episode_store import EntryEpisodeStore
from services.research.gold_s30_execution import account_fingerprint


class EpisodeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'ledger.json'
        self.account=SimpleNamespace(login=123, server='demo', trade_mode=0)
        self.identity=account_fingerprint(self.account)

    def store(self):
        return EntryEpisodeStore(self.path,self.identity)

    def test_reservation_persists_before_send_and_blocks_restart_repetition(self):
        first=self.store()
        first.reserve('break:100', 'BUY', now=100.)
        restored=self.store()
        self.assertTrue(restored.blocks('break:100','BUY'))
        self.assertTrue(restored.blocks('break:105','BUY'))
        self.assertEqual(restored.status()['outstanding'],1)

    def test_reported_done_needs_matching_broker_deal(self):
        store=self.store()
        store.reserve('break:100','BUY',now=100.)
        store.acknowledge('break:100','BUY',dict(success=True,deal=50,order=40))
        mt5=Mock()
        mt5.account_info.return_value=self.account
        mt5.history_deals_get.return_value=[]
        store.reconcile(mt5,now=101.)
        self.assertEqual(store.status()['outstanding'],1)
        mt5.history_deals_get.return_value=[SimpleNamespace(symbol='XAUUSD',magic=631011,
            entry=0,type=0,volume=.01,ticket=50)]
        store.reconcile(mt5,now=102.)
        restored=self.store()
        self.assertEqual(restored.status()['outstanding'],0)
        self.assertTrue(restored.blocks('break:100','BUY'))
        self.assertEqual(restored.blocks('break:105','BUY'),[])

    def test_rejection_does_not_retry_same_event_but_allows_new_event(self):
        store=self.store()
        store.reserve('break:100','SELL',now=100.)
        store.acknowledge('break:100','SELL',dict(success=False,action='RISK_BLOCK'))
        self.assertTrue(store.blocks('break:100','SELL'))
        self.assertEqual(store.blocks('break:105','SELL'),[])

    def test_uncertain_send_and_identity_change_fail_closed(self):
        store=self.store()
        store.reserve('break:100','BUY',now=100.)
        store.acknowledge('break:100','BUY',dict(success=False,action='ORDER_EXCEPTION'))
        self.assertTrue(store.blocks('break:105','BUY'))
        with self.assertRaises(ValueError):
            EntryEpisodeStore(self.path,'different-account')
