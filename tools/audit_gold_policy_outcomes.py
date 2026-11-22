"""Attribute captured outcomes to new or carried entries after a policy change."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path


def epoch(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()


def summarize(folder,deployment,*,start_utc=None):
    cutoff=epoch(start_utc or deployment['deployed_at'])
    rows=[]
    skipped=0
    with (folder/'observations.jsonl').open(encoding='utf-8') as handle:
        for line in handle:
            try:
                row=json.loads(line)
            except json.JSONDecodeError:
                skipped+=1
                continue
            status=row.get('status',{})
            if (status.get('config',{}).get('entry_coordination_mode')=='SCALP_PRIORITY'
                    and epoch(status['updated_at'])>=cutoff):
                rows.append(row)
    if not rows:
        return dict(available=False,reason='No captured post-deployment policy samples',skipped_partial_lines=skipped)
    closed={}
    seen_entries=set()
    denials=Counter()
    errors=Counter()
    max_positions=0
    unprotected=set()
    for row in rows:
        status=row['status']
        positions=status.get('positions',[])
        max_positions=max(max_positions,len(positions))
        for p in positions:
            if p['opened_epoch']>=cutoff:
                seen_entries.add(str(p['ticket']))
            if not p.get('sl') or p['sl']<=0:
                unprotected.add(str(p['ticket']))
        errors.update(status.get('advisor_errors',{}).keys())
        for name,lane in status.get('lanes',{}).items():
            allocation=lane.get('decision',{}).get('entry_coordination',{})
            if allocation.get('enforced') and not allocation.get('allowed'):
                denials[name]+=1
                if lane.get('decision',{}).get('allowed') and not lane.get('positions'):
                    denials[name+'_UNOCCUPIED_DIRECTIONAL']+=1
            for trade in lane.get('closed_trades',[]):
                if epoch(trade['closed_at'])>=cutoff:
                    closed[str(trade['position_id'])]=dict(trade,horizon=name)
                    if epoch(trade['opened_at'])>=cutoff:
                        seen_entries.add(str(trade['position_id']))
    latest=rows[-1]['status']
    buckets={}
    for name,is_new in [('new_entries',True),('carried_entries',False)]:
        trades=[t for t in closed.values() if (epoch(t['opened_at'])>=cutoff)==is_new]
        positions=[p for p in latest.get('positions',[]) if (p['opened_epoch']>=cutoff)==is_new]
        realized=sum(t['profit'] for t in trades)
        floating=sum(p['profit'] for p in positions)
        buckets[name]=dict(closed_trades=len(trades),realized=round(realized,2),
            open_positions=len(positions),floating=round(floating,2),total=round(realized+floating,2),
            closed=trades,open_tickets=[p['ticket'] for p in positions])
    return dict(available=True,deployed_at=deployment['deployed_at'],
        cohort_start_utc=start_utc or deployment['deployed_at'],
        first_sample=rows[0]['observed_at'],latest_sample=rows[-1]['observed_at'],samples=len(rows),
        observed_new_entry_tickets=sorted(seen_entries),outcomes=buckets,
        allocation_denial_samples=dict(denials),maximum_observed_positions=max_positions,
        unprotected_observed_tickets=sorted(unprotected),advisor_error_samples=dict(errors),
        skipped_partial_lines=skipped,limitations=[
            'Observed captured positions and bounded closed histories; this is not an exhaustive broker audit.',
            'New entries are classified by normalized UTC fill time, not their later closing time.',
            'Carried outcomes do not measure the entry-allocation change.',
            'Denial samples are repeated observations, not unique opportunities or necessarily executable trades.',
            'First sample follows deployment; sampled quotes and histories may miss short-lived events.',
            'Profitability needs adequate prospective independent setups; no positive edge is inferred here.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('folder',type=Path)
    parser.add_argument('--deployment',type=Path,default=Path('data/research/entry_efficiency/coordination_scalp_priority_deployment.json'))
    parser.add_argument('--start-utc',help='Optional prospective cohort cutoff; preserves the original deployment timestamp.')
    args=parser.parse_args()
    result=summarize(args.folder,json.loads(args.deployment.read_text(encoding='utf-8-sig')),start_utc=args.start_utc)
    (args.folder/'policy_outcomes.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
