"""Historical executable-side excursions, not a counterfactual exit backtest."""
import argparse
from datetime import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text(encoding='utf-8'))
    metadata = json.loads((args.capture/'metadata.json').read_text(encoding='utf-8'))
    if audit['account_fingerprint'] != metadata['account_fingerprint']:
        raise ValueError('Account mismatch between history and quote capture')
    ticks = pd.read_parquet(args.capture/'ticks.parquet').sort_values('timestamp', kind='stable')
    stamps, bids, asks = (ticks[key].to_numpy() for key in ('timestamp', 'bid', 'ask'))
    rows, excluded = [], 0
    for trade in audit['closed_positions']:
        opened = datetime.fromisoformat(trade['opened_utc']).timestamp()
        closed = datetime.fromisoformat(trade['closed_utc']).timestamp()
        first, last = np.searchsorted(stamps, [opened, closed], side='left')
        if opened < stamps[0] or closed > stamps[-1] or first >= last:
            excluded += 1
            continue
        sign = 1 if trade['direction'] == 'BUY' else -1
        quotes = bids[first:last] if sign > 0 else asks[first:last]
        changes = sign*(quotes-trade['entry_price'])
        peak, trough = float(changes.max()), float(changes.min())
        risk = trade['initial_stop_distance']
        exposure = trade['volume']*metadata['contract_size']
        rows.append(dict(position_id=trade['position_id'], net_realized=trade['net'],
            maximum_favorable_gross_usd=peak*exposure, maximum_adverse_gross_usd=trough*exposure,
            peak_r=peak/risk if risk and risk > 0 else None,
            quote_count=int(last-first), maximum_gap_seconds=float(np.diff(stamps[first:last]).max())
            if last-first > 1 else None))
    losses = [row for row in rows if row['net_realized'] < 0]
    report = dict(read_only=True, execution_enabled=False, covered_positions=len(rows), excluded=excluded,
        losing_positions=len(losses), losers_ever_gross_positive=sum(row['maximum_favorable_gross_usd'] > 0 for row in losses),
        losers_peak_at_least_06r=sum(row['peak_r'] is not None and row['peak_r'] >= .6 for row in losses),
        rows=rows, limitations=['Observed extrema do not establish attainable fills or improved exit expectancy.',
            'No gap interpolation; report quote gaps and excluded windows.',
            'Gross excursion excludes commissions, fees and latency; realized trade net includes recorded costs.',
            'No thresholds optimized or exit-policy change justified by this reused history.'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
