"""Read-only observed protections/capacity audit; never calls the trading API."""
import argparse
import json
from pathlib import Path


def audit(folder):
    rows = []
    for line in (folder/'observations.jsonl').read_text(encoding='utf-8').splitlines():
        try:
            row = json.loads(line)
            if row.get('status') and row.get('account'):
                rows.append(row)
        except ValueError:
            continue
    samples = []
    for row in rows:
        owned = [p for p in row.get('positions') or [] if p.get('magic') == 631011]
        status = row['status']
        samples.append(dict(observed_at=row['observed_at'], count=len(owned),
            capacity=min(5,int(status.get('config',{}).get('max_positions_total',5))),
            unprotected=[p['ticket'] for p in owned if p.get('sl',0) <= 0],
            unexpected_volume=[p['ticket'] for p in owned if abs(p['volume']-.01) > 1e-9],
            mixed_directions=len({p['type'] for p in owned}) > 1,
            other_lane_positions={name:len(lane.get('positions',[]))
                for name,lane in status.get('lanes',{}).items()
                if name != 'SCALP' and lane.get('positions')},
            demo=row['account'].get('trade_mode') == 0,
            running=status.get('status') == 'RUNNING'))
    return dict(observations=len(samples), first_sample=rows[0]['observed_at'],
        last_sample=rows[-1]['observed_at'],
        maximum_owned_positions=max(s['count'] for s in samples),
        samples_at_capacity=sum(s['count'] == s['capacity'] for s in samples),
        capacity_violation_samples=sum(s['count'] > s['capacity'] for s in samples),
        unprotected_samples=[s for s in samples if s['unprotected']],
        unexpected_volume_samples=[s for s in samples if s['unexpected_volume']],
        mixed_direction_samples=sum(s['mixed_directions'] for s in samples),
        secondary_position_samples=[s for s in samples if s['other_lane_positions']],
        non_demo_samples=sum(not s['demo'] for s in samples),
        non_running_samples=sum(not s['running'] for s in samples),
        limitations=['Ten-second observations cannot certify every intervening tick/order.',
            'Observed stop presence does not guarantee a fill at that stop price.',
            'Maximum observed capacity is usage, not proof that every permitted addition qualified.',
            'Owned positions are identified by main SCALP magic 631011.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder',type=Path)
    folder = parser.parse_args().folder
    result = audit(folder)
    (folder/'constraints_audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
