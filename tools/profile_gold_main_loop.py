"""Read-only sampling of unique published main-bot processing measurements."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import statistics
import time


def distribution(values):
    values=sorted(values)
    return dict(samples=len(values),median=statistics.median(values),
                p95=values[min(len(values)-1,int(len(values)*.95))],maximum=max(values))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--seconds',type=float,default=120)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    output=root/'data/research/entry_efficiency/loop_profiles'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output.mkdir(parents=True,exist_ok=True)
    samples=[]
    previous=None
    errors=0
    started=time.monotonic()
    while time.monotonic()-started<args.seconds:
        try:
            status=json.loads((root/'data/runtime/gold_consensus_status.json').read_text(encoding='utf-8'))
            stamp=status.get('updated_at')
            if stamp!=previous and status.get('phase_timings_ms'):
                previous=stamp
                sample=dict(updated_at=stamp,cycle=status['cycle'],loop_elapsed_ms=status['loop_elapsed_ms'],
                            previous_status_write_ms=status.get('previous_status_write_ms'),
                            phase_timings_ms=status['phase_timings_ms'],advisor_errors=status.get('advisor_errors',{}))
                samples.append(sample)
                with (output/'samples.jsonl').open('a',encoding='utf-8') as handle:
                    handle.write(json.dumps(sample)+'\n')
        except (OSError,ValueError,KeyError):
            errors+=1
        time.sleep(.2)
    phases={name:distribution([s['phase_timings_ms'][name] for s in samples if name in s['phase_timings_ms']])
            for name in sorted({name for s in samples for name in s['phase_timings_ms']})}
    report=dict(seconds=time.monotonic()-started,unique_cycles=len(samples),read_errors=errors,
        phases=phases,loop=distribution([s['loop_elapsed_ms'] for s in samples]) if samples else None,
        status_write=distribution([s['previous_status_write_ms'] for s in samples]) if samples else None,
        slowest=sorted(samples,key=lambda s:s['loop_elapsed_ms'],reverse=True)[:5],
        limitations=['Published-cycle sampling may miss cycles; stage wall time includes CPU scheduling and contention.',
                     'Loop processing excludes the current status write and configured sleep.',
                     'Status-write measurement describes the preceding published cycle.'])
    (output/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(path=str(output),**report),indent=2))


if __name__=='__main__':
    main()
