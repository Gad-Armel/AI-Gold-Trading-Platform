"""Read-only, fixed-cadence forward observations of the unified Gold dashboard."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interval', type=float, default=35)
    parser.add_argument('--samples', type=int, default=50)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.interval < 1 or args.samples < 1:
        parser.error('Positive samples and interval >= 1 required')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    with args.output.open('a', encoding='utf-8', buffering=1) as stream:
        for index in range(args.samples):
            delay = began + index * args.interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            row = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'sample': index}
            try:
                with urlopen('http://127.0.0.1:8777/api/unified', timeout=8) as response:
                    payload = json.load(response)
                # Never persist the browser's control token.
                native = payload.get('native') or {}
                consensus = payload.get('consensus') or {}
                row.update({
                    'state': native.get('state'),
                    'age_seconds': native.get('age_seconds'),
                    'snapshot': native.get('snapshot'),
                    'consensus_state': consensus.get('state'),
                })
                snap = row.get('snapshot') or {}
                print(json.dumps({'sample': index, 'state': row['state'], 'version': snap.get('version'),
                                  'status': snap.get('status'), 'positions': len(snap.get('positions', [])),
                                  'kpi': snap.get('kpi'), 'consensus_state': row['consensus_state']}), flush=True)
            except (OSError, ValueError) as exc:
                row['error'] = str(exc)
                print(json.dumps({'sample': index, 'error': str(exc)}), flush=True)
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
