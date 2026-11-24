"""Point-in-time evidence for forward evaluation, with daily quote files."""
import json
from datetime import datetime, timezone
from pathlib import Path


class GoldResearchRecorder:
    def __init__(self, root='data/research/gold_forward'):
        self.root=Path(root)
        self.last_quote=None
        self.last_signatures={}
        self.last_recorded={}

    def record(self, snapshot, lanes, news):
        self.root.mkdir(parents=True,exist_ok=True)
        now=datetime.now(timezone.utc)
        quote=(snapshot.tick_time_msc,snapshot.bid,snapshot.ask)
        if quote != self.last_quote:
            with (self.root/f'quotes_{now:%Y%m%d}.jsonl').open('a',encoding='utf-8') as handle:
                handle.write(json.dumps(dict(observed_at=now.isoformat(),broker_time_msc=quote[0],
                    bid=quote[1],ask=quote[2],quote_age_seconds=snapshot.quote_age_seconds))+'\n')
            self.last_quote=quote
        for name,lane in lanes.items():
            context=lane.get('adaptive_market',{})
            bar=context.get('bar_id')
            decision=lane['decision']
            # Ignore refresh timestamps and decaying quality in the signature;
            # preserve genuinely new publications and corrected release values.
            events=[{key:event.get(key) for key in
                     ('event_time','title','source','actual','forecast','previous','reaction_eligible')}
                    for event in news.get('relevant_events',[]) if isinstance(event,dict)]
            signature=json.dumps(dict(bar=bar,allowed=decision.get('allowed'),
                direction=decision.get('direction'),bias=decision.get('dominant_bias'),
                smc=dict(feature_epoch=decision.get('smc_strategy', {}).get('feature_epoch'),
                    candidates=[(candidate.get('id'), candidate.get('eligible'), candidate.get('blocks'))
                                for candidate in decision.get('smc_strategy', {}).get('candidates', [])]),
                news_block=decision.get('news_block'),economic_conflict=decision.get('economic_conflict'),
                cross_market_bar=decision.get('cross_market',{}).get('bar_id'),
                cross_market_bias=decision.get('cross_market',{}).get('gold_bias'),
                timing=lane['entry_timing_ready'],events=sorted(events,key=lambda e:json.dumps(e,sort_keys=True,default=str)),
                positions=sorted(p['ticket'] for p in lane.get('positions',[])),
                exit_reason=lane.get('adaptive_exit',{}).get('reason')),sort_keys=True,default=str)
            # Open-position examples at loop cadence are needed to evaluate
            # holding versus closing. A flat scalp heartbeat records flow even
            # when its categorical entry decision has not changed.
            heartbeat = 2.0 if lane.get('positions') else 10.0
            due = name == 'SCALP' and now.timestamp()-self.last_recorded.get(name,0) >= heartbeat
            if not bar or (self.last_signatures.get(name)==signature and not due):continue
            with (self.root/f'decisions_{now:%Y%m%d}.jsonl').open('a',encoding='utf-8') as handle:
                handle.write(json.dumps(dict(observed_at=now.isoformat(),horizon=name,market=context,
                    decision=lane['decision'],entry_timing_ready=lane['entry_timing_ready'],
                    positions=lane.get('positions',[]),adaptive_exit=lane.get('adaptive_exit',{}),
                    micro_flow=lane.get('micro_flow',{}),entry_timing_blocks=lane.get('entry_timing_blocks',[]),
                    entries_last_hour=lane.get('entries_last_hour'),consecutive_losses=lane.get('consecutive_losses'),
                    bid=snapshot.bid,ask=snapshot.ask,news=news),default=str)+'\n')
            self.last_signatures[name]=signature
            self.last_recorded[name]=now.timestamp()
