"""Observational before/after latency comparison; not a controlled profit test."""
import json
import statistics
import sys
from pathlib import Path


def main():
    folder = Path(sys.argv[1])
    groups = {'before_context_cache': [], 'after_context_cache': []}
    for line in (folder/'observations.jsonl').open(encoding='utf-8'):
        row = json.loads(line)
        status = row.get('status', {})
        latency = status.get('loop_elapsed_ms')
        if not isinstance(latency, (int, float)) or status.get('status') != 'RUNNING':
            continue
        cache = status.get('exit_context_cache')
        if cache is not None and cache.get('hits', 0)<10:
            continue
        groups['after_context_cache' if cache is not None else 'before_context_cache'].append(latency)
    report = dict(groups={key: dict(samples=len(values),
        median_ms=round(statistics.median(values), 2) if values else None,
        p95_ms=round(sorted(values)[int((len(values)-1)*.95)], 2) if values else None)
        for key, values in groups.items()},
        limitation='Different market times and CPU load; isolated paired benchmark is the stronger attribution evidence.')
    (folder/'latency_comparison.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
