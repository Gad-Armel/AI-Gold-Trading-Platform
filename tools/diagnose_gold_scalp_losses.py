"""Describe confirmed demo trade outcomes and their recorded close policies."""
from collections import defaultdict
from datetime import datetime,timezone
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
broker=json.loads((root/'data/research/blueprint_review_20261009/live_broker_audit.json').read_text())
events=[]
for line in (root/'data/demo/gold_consensus_demo_journal.jsonl').read_text().splitlines():
    try:events.append(json.loads(line))
    except ValueError:pass
close={e['position_ticket']:e for e in events if e.get('record_type')=='CLOSE' and e.get('success')}
entry={e.get('order'):e for e in events if e.get('record_type')=='HORIZON_OPEN' and e.get('success')}
trades=broker['cohorts']['scalp_only']['trades']
groups=defaultdict(list)
directions=defaultdict(list)
high=[]
for trade in trades:
    ticket=trade['position_id']
    reason=close.get(ticket,{}).get('reason') or trade['close_comment'] or 'UNATTRIBUTED'
    groups[reason].append(trade['profit'])
    directions[trade['direction']].append(trade['profit'])
    if (entry.get(ticket,{}).get('evidence') or 0)>=85:
        high.append(trade['profit'])
def stats(values):
    wins=[v for v in values if v>0];losses=[v for v in values if v<0]
    return dict(trades=len(values),net=round(sum(values),2),wins=len(wins),losses=len(losses),
        average_win=sum(wins)/len(wins) if wins else None,
        average_loss=-sum(losses)/len(losses) if losses else None)
status=json.loads((root/'data/runtime/gold_consensus_status.json').read_text())
report=dict(as_of=broker['as_of'],overall=stats([t['profit'] for t in trades]),
    directions={k:stats(v) for k,v in directions.items()},
    exits={k:stats(v) for k,v in sorted(groups.items(),key=lambda item:sum(item[1]))},
    primary_evidence_at_least_85=stats(high),
    current={name:dict(direction=l['decision']['direction'],evidence=l['decision']['evidence'])
             for name,l in status['lanes'].items()},
    limitations=['Broker-confirmed position outcomes; journal reasons can describe basket-wide triggers.',
        'Broker SL comments are recorded, not classified solely by dollar loss.',
        'Entry order/position IDs coincide here; absent matches are excluded from score subgroup.',
        'Short descriptive cohort, not a counterfactual test of removing stops.'])
folder=root/'data/research/scalp_loss_diagnosis_20261009';folder.mkdir(exist_ok=True)
(folder/'diagnosis.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
