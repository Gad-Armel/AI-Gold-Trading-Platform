"""Read-only broker tick export and executable markouts for a completed monitor."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from config import gold_consensus_settings as settings
from services.market_data.gold_broker_clock import to_broker_time
from services.research.gold_s30_execution import account_fingerprint
from services.research.gold_tick_markout import validate_ticks, executable_markout
from services.utils.atomic_json import atomic_write_json


def summarize_samples(samples, ticks):
    results = []
    for horizon in (5, 15, 30):
        for cohort in ('directional', 'all_entry_checks_ready'):
            outcomes = []
            for sample in samples:
                direction = sample.get('direction')
                if direction not in ('BUY', 'SELL') or sample.get('status') != 'RUNNING':
                    continue
                if cohort == 'all_entry_checks_ready' and not (sample.get('allowed') and sample.get('entry_ready')):
                    continue
                observed = datetime.fromisoformat(sample['observed_at']).timestamp()
                updated = datetime.fromisoformat(sample['updated_at']).timestamp()
                if not 0 <= observed-updated <= 5:
                    continue
                outcome = executable_markout(ticks, observed, direction, horizon_seconds=horizon,
                    latency_seconds=.25, commission_price=.1, slippage_price=.2)
                if outcome is not None:
                    outcomes.append(outcome)
            count = len(outcomes)
            results.append(dict(horizon_seconds=horizon, cohort=cohort, observations=count,
                midpoint_direction_hit_fraction=sum(row['main_net_price'] > row['inverse_net_price']
                    for row in outcomes)/count if count else None,
                net_positive_fraction=sum(row['main_net_price'] > 0 for row in outcomes)/count if count else None,
                mean_net_price=sum(row['main_net_price'] for row in outcomes)/count if count else None))
    return results


def main():
    import MetaTrader5 as mt5
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    args = parser.parse_args()
    root = Path(args.directory)
    report = json.loads((root/'report.json').read_text(encoding='utf-8'))
    if not report.get('account_continuity'):
        raise RuntimeError('A completed observation with stable demo identity is required')
    start, end = (datetime.fromisoformat(report[key]) for key in ('started', 'ended'))
    if not mt5.initialize(timeout=5000):
        raise RuntimeError(mt5.last_error())
    try:
        account = mt5.account_info()
        if (account is None or account.trade_mode != 0
                or account_fingerprint(account) != report['initial_broker']['account_fingerprint']):
            raise RuntimeError('Original demo account required')
        raw = mt5.copy_ticks_range('XAUUSD', to_broker_time(start), to_broker_time(end), mt5.COPY_TICKS_ALL)
        if raw is None or not len(raw):
            raise RuntimeError(f'Tick history unavailable: {mt5.last_error()}')
        frame = pd.DataFrame(dict(timestamp=raw['time_msc']/1000.-settings.MT5_SERVER_UTC_OFFSET_SECONDS,
                                  bid=raw['bid'], ask=raw['ask']))
        valid = np.isfinite(frame.to_numpy()).all(axis=1) & (frame.bid > 0) & (frame.ask >= frame.bid)
        frame = frame[valid & (frame.timestamp >= start.timestamp()) & (frame.timestamp <= end.timestamp())]
        frame = validate_ticks(frame)
        frame.to_csv(root/'observed_ticks.csv', index=False)
    finally:
        mt5.shutdown()
    samples = [json.loads(line) for line in (root/'samples.jsonl').read_text(encoding='utf-8').splitlines()]
    audit = dict(role='OBSERVATIONAL_MARKOUTS_NOT_PRODUCTION_STRATEGY_ACCURACY',
        broker_ticks=len(raw), usable_ticks=len(frame), sampled_status_rows=len(samples),
        assumptions=dict(per_leg_latency_seconds=.25, commission_price=.1, slippage_price=.2,
                         costs='Provisional round-trip price equivalents; not measured fill guarantees'),
        results=summarize_samples(samples, frame),
        notes=['Overlapping observations are not independent trades.',
               'Directional movement and executable net profits are different metrics.',
               'Rejected signals are not trades; adaptive exits/SLs are not simulated.',
               'Twenty minutes cannot validate a calibrated model or long-term profitability.'])
    atomic_write_json(root/'signal_audit.json', audit)
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    main()
