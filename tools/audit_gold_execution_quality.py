"""Reconcile journal telemetry to actual captured broker deals; read-only."""
import argparse
import json
from datetime import datetime
from pathlib import Path
import statistics


def audit(folder, journal, start_utc):
    cutoff = datetime.fromisoformat(start_utc)
    capture = json.loads((folder/'latest.json').read_text())
    deals = {int(d['ticket']):d for d in capture.get('deals') or []}
    records = []
    unbound = []
    incomplete = 0
    for line in journal.read_text(encoding='utf-8').splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            incomplete += 1
            continue
        stamp = row.get('timestamp_utc')
        if not stamp or datetime.fromisoformat(stamp) < cutoff:
            continue
        kind = row.get('record_type')
        if kind not in ('HORIZON_OPEN','CLOSE'):
            continue
        metric = row.get('execution_metrics')
        if not metric:
            continue
        deal = deals.get(int(row.get('deal') or 0))
        if not deal:
            # A journal can also contain old offline test fixtures. An accepted
            # response without a matching broker deal is not fill evidence.
            unbound.append(dict(kind=kind, timestamp=stamp, deal=row.get('deal'),
                                success=row.get('success'), state=metric.get('state')))
            continue
        side = (1 if row.get('direction') == 'BUY' else -1) if kind == 'HORIZON_OPEN' else None
        if kind == 'CLOSE' and deal:
            side = 1 if deal.get('type') == 0 else -1
        requested = row.get('entry_price') if kind == 'HORIZON_OPEN' else row.get('requested_price')
        actual_slip = side*(deal['price']-requested) if deal and side is not None and requested else None
        reported = metric.get('reported_price')
        records.append(dict(timestamp=stamp, kind=kind, deal=row.get('deal'),
                            success=row.get('success'), latency_ms=metric.get('order_send_elapsed_ms'),
                            execution_state=metric.get('state'), requested_price=requested,
                            reported_price=reported, actual_deal_price=deal['price'] if deal else None,
                            confirmed_by_history=bool(deal),
                            actual_adverse_price_slippage=actual_slip,
                            reported_matches_history=abs(reported-deal['price']) < 1e-8 if reported and deal else None,
                            actual_volume=deal['volume'] if deal else None,
                            deal_charges=sum(deal.get(k,0) for k in ('commission','swap','fee')) if deal else None))
    summary = {}
    for kind in ('HORIZON_OPEN','CLOSE'):
        group = [r for r in records if r['kind'] == kind]
        latency = sorted(r['latency_ms'] for r in group if r['latency_ms'] is not None)
        slip = [r['actual_adverse_price_slippage'] for r in group if r['confirmed_by_history']]
        summary[kind] = dict(attempts=len(group), confirmed_deals=sum(r['confirmed_by_history'] for r in group),
            median_order_send_ms=statistics.median(latency) if latency else None,
            maximum_order_send_ms=max(latency) if latency else None,
            mean_actual_adverse_price_slippage=statistics.mean(slip) if slip else None,
            reported_price_mismatches=sum(r['reported_matches_history'] is False for r in group))
    return dict(as_of=capture['observed_at'], start_utc=start_utc, summary=summary, records=records,
                unbound_journal_records=unbound,
                incomplete_journal_lines=incomplete, limitations=[
                    'Latency times the order_send call; it is not network ping or whole decision latency.',
                    'Actual deal history has priority over the broker response price.',
                    'Missing returned deal does not prove rejection; pending/partial results need further reconciliation.',
                    'Selected returned deals only: multiple partial fill deals are not reconstructed here.',
                    'Adverse slippage sign follows submitted order side, including opposite-side closes.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder',type=Path)
    parser.add_argument('--start-utc',default='2026-10-09T05:58:31+00:00')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = audit(args.folder,root/'data/demo/gold_consensus_demo_journal.jsonl',args.start_utc)
    (args.folder/'execution_quality.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k != 'records'},indent=2))
