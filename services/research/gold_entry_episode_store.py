"""Durable account-bound request/fill ledger; uncertainty blocks new entries."""
import json
import math
from pathlib import Path
from datetime import datetime, timedelta, timezone
from services.research.gold_entry_episode import EntryEpisodeGuard
from services.utils.atomic_json import atomic_write_json


class EntryEpisodeStore:
    def __init__(self, path, identity):
        if not isinstance(identity, str) or not identity:
            raise ValueError('Account identity required')
        self.path, self.identity = Path(path), identity
        self.guard = EntryEpisodeGuard()
        self.requests = []
        if self.path.exists():
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if value.get('version') != 1 or value.get('account_fingerprint') != identity:
                raise ValueError('Entry ledger identity mismatch; do not delete to bypass')
            self.guard.restore(value['confirmed'])
            rows = value['requests']
            if not isinstance(rows, list) or len(rows)>200:
                raise ValueError('Invalid entry request ledger')
            seen = set()
            for r in rows:
                key = (r['setup_id'], r['direction'])
                if (self.guard._key(*key) is None or key in seen or
                    r['state'] not in ('RESERVED','REPORTED','CONFIRMED','REJECTED','UNCERTAIN') or
                    isinstance(r['created_at'], bool) or not isinstance(r['created_at'], (int,float)) or not math.isfinite(r['created_at']) or r['created_at']<=0 or
                    any(isinstance(r[k], bool) or not isinstance(r[k], int) or r[k]<0 for k in ('deal_id','order_id'))):
                    raise ValueError('Invalid entry request record')
                seen.add(key)
            self.requests = rows

    def save(self):
        atomic_write_json(self.path, dict(version=1,account_fingerprint=self.identity,
                          confirmed=self.guard.snapshot(),requests=self.requests))

    def blocks(self, setup_id, direction):
        blocks = self.guard.blocks(setup_id,direction)
        if any(r['state'] in ('RESERVED','REPORTED','UNCERTAIN') for r in self.requests):
            blocks.append('Waiting for broker reconciliation of an outstanding entry request.')
        if any(r['setup_id']==setup_id and r['direction']==direction for r in self.requests):
            blocks.append('This price event already had an order request; wait for a new event.')
        return blocks

    def reserve(self, setup_id, direction, *, now):
        if isinstance(now, bool) or not isinstance(now, (int,float)) or not math.isfinite(now) or now<=0:
            raise ValueError('Finite positive request time required')
        blocks = self.blocks(setup_id,direction)
        if blocks:
            raise ValueError(' | '.join(blocks))
        self.requests.append(dict(setup_id=setup_id,direction=direction,created_at=now,
                                  state='RESERVED',deal_id=0,order_id=0))
        self.requests = self.requests[-200:]
        self.save()  # Persist before any broker send.

    def acknowledge(self, setup_id, direction, result):
        row = next(r for r in reversed(self.requests) if (r['setup_id'],r['direction'])==(setup_id,direction))
        row.update(deal_id=int(result.get('deal') or 0),order_id=int(result.get('order') or 0))
        row['state'] = ('REPORTED' if result.get('success') else
                        'UNCERTAIN' if result.get('action')=='ORDER_EXCEPTION' else 'REJECTED')
        self.save()

    def reconcile(self, mt5, *, now):
        from services.research.gold_s30_execution import account_fingerprint
        from services.market_data.gold_broker_clock import to_broker_time
        account=mt5.account_info()
        if account is None or account_fingerprint(account)!=self.identity or account.trade_mode!=0:
            raise ValueError('Account changed while reconciling entry ledger')
        changed=False
        for row in self.requests:
            if row['state'] not in ('RESERVED','REPORTED','UNCERTAIN'):
                continue
            if row['deal_id']:
                deals=mt5.history_deals_get(ticket=row['deal_id'])
            elif row['order_id']:
                start=datetime.fromtimestamp(row['created_at']-5,timezone.utc)
                end=datetime.fromtimestamp(now+1,timezone.utc)
                values=mt5.history_deals_get(to_broker_time(start),to_broker_time(end))
                deals=[d for d in values or [] if d.order==row['order_id']]
            else:
                continue  # Crash/timeout before acknowledgement requires explicit reconciliation.
            matches=[d for d in deals or [] if d.symbol=='XAUUSD' and d.magic==631011
                     and d.entry==0 and d.type==(0 if row['direction']=='BUY' else 1)
                     and 0<float(d.volume)<=.01000001]
            if matches:
                deal=int(matches[0].ticket)
                self.guard.record_fill(row['setup_id'],row['direction'],deal_id=deal,confirmed=True)
                row.update(state='CONFIRMED',deal_id=deal)
                changed=True
        if changed:
            self.save()

    def status(self):
        return dict(confirmed_events=self.guard.snapshot()['filled_setup_count'],
                    outstanding=sum(r['state'] in ('RESERVED','REPORTED','UNCERTAIN') for r in self.requests),
                    tracked_requests=len(self.requests))
