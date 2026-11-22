"""Summarize recorded observation windows without claiming unobserved uptime."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import numpy as np


def main():
    root = Path(__file__).resolve().parents[1]
    research = root/'data/research/strategy_20261021'
    windows = []
    for name in ('20261021T100648Z', '20261021T173105Z'):
        rows = [json.loads(line) for line in (root/'data/monitoring'/name/'observations.jsonl').read_text(encoding='utf-8').splitlines()]
        first, last = (datetime.fromisoformat(rows[index]['observed_at']) for index in (0, -1))
        loops = [row['status']['loop_elapsed_ms'] for row in rows if 'status' in row]
        windows.append(dict(path=f'data/monitoring/{name}', samples=len(rows), first=first.isoformat(),
            last=last.isoformat(), observed_span_seconds=(last-first).total_seconds(),
            observation_errors=sum(bool(row.get('error')) for row in rows),
            maximum_observed_open_positions=max(len(row.get('positions') or []) for row in rows),
            loop_median_ms=float(np.median(loops)), loop_p95_ms=float(np.quantile(loops, .95))))
    inventory = json.loads((root/'data/research/project_cleanup/inventory_before.json').read_text())
    protected = [item for item in inventory['files'] if item.get('category') == 'protected_advisor1']
    changed = [item['path'] for item in protected if
               hashlib.sha256((root/item['path']).read_bytes()).hexdigest() != item['sha256']]
    status = json.loads((root/'data/runtime/gold_consensus_status.json').read_text(encoding='utf-8'))
    report = dict(as_of=datetime.now(timezone.utc).isoformat(), read_only=True, monitoring_windows=windows,
        total_recorded_observation_minutes=sum(window['observed_span_seconds'] for window in windows)/60,
        continuous_monitoring_during_conversation_gap=False,
        advisor1_protected_files=len(protected), advisor1_changed_files=changed,
        main=dict(status=status['status'], updated_at=status['updated_at'], mode=status['mode'],
            positions=len(status['positions']), advisor_errors=status['advisor_errors'],
            research_entry_hold=status['config'].get('research_entry_hold'),
            lot=status['config']['lot_size'], maximum_positions=status['config']['max_positions_total']),
        strategy_promoted_to_execution=False, profitable_strategy_validated=False,
        forward_trials={})
    for name in ('forward', 'orbit_forward'):
        data = json.loads((research/name/'latest.json').read_text())
        report['forward_trials'][name] = dict(observed_at=data['observed_at'],
            duration_seconds=data['duration_seconds'], paper_summary=data['paper_result']['summary'],
            censored_positions=data['paper_result']['censored_positions'],
            completed=data.get('completed'), completed_at=data.get('completed_at'),
            note='Paper-only; quotes/latency/cost assumptions, not broker trade performance')
    (research/'final_review.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
