"""Describe executed review-window entries using only prior captured context."""
import argparse
import bisect
from collections import Counter
from datetime import datetime
import json
from pathlib import Path


def epoch(value):
    return datetime.fromisoformat(value).timestamp()


def audit(folder, journal):
    rows = []
    for line in (folder/'observations.jsonl').read_text().splitlines():
        try:
            row = json.loads(line)
            if row.get('status',{}).get('updated_at'):
                rows.append(row)
        except ValueError:
            continue
    stamps = [max(epoch(r['observed_at']),epoch(r['status']['updated_at'])) for r in rows]
    latest = rows[-1]
    deals = {d['ticket']:d for d in latest.get('deals') or []}
    outcomes = {t['position_id']:t for name,lane in latest['status']['lanes'].items()
                for t in lane.get('closed_trades',[])}
    entries = []
    for line in journal.read_text().splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if item.get('record_type') != 'HORIZON_OPEN' or not item.get('success'):
            continue
        deal = deals.get(item.get('deal'))
        if not deal:
            continue
        # Connected broker history is UTC+3; capture records normalize settings.
        offset = latest['status']['config'].get('broker_utc_offset_seconds',10800)
        opened = deal.get('time_msc',deal['time']*1000)/1000-offset
        if opened < stamps[0]:
            continue
        index = bisect.bisect_right(stamps,opened)-1
        if index < 0:
            continue
        prior = rows[index]['status']['lanes'].get(item['horizon'],{})
        context = prior.get('adaptive_market',{})
        setup = prior.get('decision',{}).get('setup_observation',{})
        ticket = deal['position_id']
        profits, peaks = [], []
        for row in rows[index:]:
            for p in row['status'].get('positions',[]):
                if p['ticket'] == ticket:
                    profits.append(p['profit'])
                    if p.get('peak_profit_usd') is not None:
                        peaks.append(p['peak_profit_usd'])
        trade = outcomes.get(ticket)
        entries.append(dict(ticket=ticket,opened_epoch=opened, side=item['direction'],
            evidence=item.get('evidence'),net_profit=trade['profit'] if trade else None,
            outcome='CLOSED' if trade else 'OPEN_OR_HISTORY_UNAVAILABLE',
            analysis_reward_risk=item.get('entry_context',{}).get('analysis_reward_risk'),
            analysis_target_distance_from_fill=abs(item['analysis_tp']-deal['price']),
            planned_stop_distance_from_fill=abs(deal['price']-item['sl']),
            spread_at_request=item.get('entry_context',{}).get('quote',{}).get('ask',0)
                              -item.get('entry_context',{}).get('quote',{}).get('bid',0),
            prior_context_lag_seconds=opened-stamps[index],
            prior_m1_trend=context.get('trend'), prior_m1_momentum=context.get('momentum'),
            prior_m1_regime=context.get('structure_research',{}).get('regime'),
            prior_m5_setup_regime=setup.get('regime') if setup.get('available') else None,
            maximum_published_peak=max(peaks) if peaks else None,
            maximum_sampled_profit=max(profits) if profits else None,
            minimum_sampled_profit=min(profits) if profits else None))
    return dict(first_sample=rows[0]['observed_at'],as_of=latest['observed_at'],entries=entries,
                count=len(entries),prior_regimes=dict(Counter(e['prior_m1_regime'] for e in entries)),
                limitations=['Only executed entries with returned deals in the capture are included.',
                             'Prior context uses both observation and status clocks strictly before the actual fill.',
                             'Ten-second sampling can lag a trigger bar; this is descriptive, not precise signal replay.',
                             'Published peaks begin after telemetry deployment; sampled peaks underestimate true tick maxima.',
                             'Analysed target is a scenario used by the entry gate; the adaptive bot has no fixed target order.',
                             'No threshold is optimized or execution rule changed by this retrospective description.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder',type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = audit(args.folder,root/'data/demo/gold_consensus_demo_journal.jsonl')
    (args.folder/'entry_context_audit.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
