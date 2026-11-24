"""Cross-check main entry journals against captured broker deals; read-only."""
import argparse
import json
from pathlib import Path
import statistics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    capture = json.loads((args.folder / 'latest.json').read_text())
    deals = {int(deal['ticket']): deal for deal in capture.get('deals', [])}
    root = Path(__file__).resolve().parents[1]
    rows = []
    missing = []
    for line in (root / 'data/demo/gold_consensus_demo_journal.jsonl').open(encoding='utf-8'):
        entry = json.loads(line)
        if entry.get('record_type') != 'HORIZON_OPEN' or not entry.get('success') or not entry.get('entry_context'):
            continue
        deal = deals.get(int(entry.get('deal') or 0))
        if deal is None:
            missing.append(entry.get('order'))
            continue
        sign = 1 if entry['direction'] == 'BUY' else -1
        actual = float(deal['price'])
        requested = float(entry['entry_price'])
        reported = entry.get('broker_reported_price')
        rows.append(dict(order=entry['order'], deal=deal['ticket'], lane=entry['horizon'],
            direction=entry['direction'], requested=requested, broker_reported=reported,
            deal_price=actual, adverse_price_slippage=round(sign * (actual - requested), 6),
            reported_price_matches_deal=reported is not None and abs(float(reported) - actual) < 1e-8,
            deal_volume=deal['volume'], reported_volume=entry.get('broker_reported_volume'),
            quote_age_seconds=entry['entry_context']['quote']['age_seconds'],
            entry_deal_charges=sum(float(deal.get(key) or 0) for key in ('commission', 'swap', 'fee'))))
    groups = []
    for lane in ('SCALP', 'INTRADAY', 'SWING', 'ALL'):
        sample = [row for row in rows if lane == 'ALL' or row['lane'] == lane]
        groups.append(dict(lane=lane, entries=len(sample),
            reported_price_mismatches=sum(not row['reported_price_matches_deal'] for row in sample),
            mean_adverse_price_slippage=round(statistics.mean(row['adverse_price_slippage'] for row in sample), 6) if sample else None,
            median_quote_age_seconds=statistics.median(row['quote_age_seconds'] for row in sample) if sample else None,
            entry_deal_charges=round(sum(row['entry_deal_charges'] for row in sample), 4)))
    report = dict(observed_at=capture['observed_at'], rows=rows, groups=groups,
        missing_deal_orders=missing, limitations=[
            'Only post-instrumentation successful journal entries with matching captured deals are measured.',
            'Negative adverse slippage means a better price; it is not prediction profit or a positive strategy edge.',
            'Price differences are instrument price units; dollar impact depends on contract size and volume.',
            'Partial fills can generate several deals; this check matches the specific returned deal only.',
            'Entry charges exclude later closing charges; observed broker quote age is not measured execution latency.'])
    (args.folder / 'entry_execution_audit.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
