"""Bounded read-only demo observation; never submits or changes orders."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.dashboard.gold_consensus_web import read_dashboard_status
from services.market_data.gold_broker_clock import to_broker_time, quote_age
from services.research.gold_s30_execution import account_fingerprint
from services.utils.atomic_json import atomic_write_json


def broker_snapshot(start=None, *, terminal_path=None, expected_fingerprint=None):
    import MetaTrader5 as mt5
    if not mt5.initialize(*([terminal_path] if terminal_path else []), timeout=5000):
        return dict(available=False, error=str(mt5.last_error()))
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            return dict(available=False, error='Demo account required')
        if expected_fingerprint and account_fingerprint(account)!=expected_fingerprint:
            return dict(available=False,error='Observation account identity mismatch')
        rows = mt5.positions_get(symbol='XAUUSD')
        if rows is None:
            return dict(available=False, error='Positions unavailable')
        positions = [dict(ticket=row.ticket, magic=row.magic, volume=row.volume,
                          floating=row.profit+row.swap, sl=row.sl) for row in rows
                     if row.magic in (631011, 631021)]
        tick = mt5.symbol_info_tick('XAUUSD')
        result = dict(available=True, account_fingerprint=account_fingerprint(account),
                      positions=positions, quote_age=quote_age(tick.time_msc/1000) if tick else None)
        if start is not None:
            deals = mt5.history_deals_get(to_broker_time(start), to_broker_time(datetime.now(timezone.utc)))
            result['history_available'] = deals is not None
            result['deals'] = [dict(ticket=row.ticket, position_id=row.position_id, magic=row.magic,
                entry=row.entry, volume=row.volume, net=row.profit+row.commission+row.swap+row.fee)
                for row in deals or [] if row.symbol == 'XAUUSD' and row.magic in (631011, 631021)]
        return result
    finally:
        mt5.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minutes', type=float, default=20.)
    parser.add_argument('--interval', type=float, default=5.)
    parser.add_argument('--output', default='data/research/gold_live_monitor')
    parser.add_argument('--terminal-path')
    parser.add_argument('--expected-account-fingerprint')
    args = parser.parse_args()
    if not 0 < args.minutes <= 120 or not 1 <= args.interval <= 60:
        parser.error('Use 0–120 minutes and a 1–60 second interval')
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    if any((root/name).exists() for name in ('samples.jsonl', 'progress.json', 'report.json')):
        raise ValueError('Choose a fresh output directory; never mix observation windows')
    started = datetime.now(timezone.utc)
    initial = broker_snapshot(terminal_path=args.terminal_path, expected_fingerprint=args.expected_account_fingerprint)
    deadline = time.monotonic()+args.minutes*60
    blocks, directions = Counter(), Counter()
    samples, errors, position_tickets = 0, [], set()
    with (root/'samples.jsonl').open('a', encoding='utf-8') as handle:
        while True:
            try:
                status = read_dashboard_status()
                lane = status.get('lanes', {}).get('SCALP', {})
                decision = lane.get('decision', {})
                reasons = list(dict.fromkeys(decision.get('blocks', [])+lane.get('entry_timing_blocks', [])))
                blocks.update(reasons)
                directions.update([decision.get('direction', 'UNKNOWN')])
                positions = status.get('positions', [])
                position_tickets.update(str(row.get('ticket')) for row in positions)
                row = dict(observed_at=datetime.now(timezone.utc).isoformat(),
                    updated_at=status.get('updated_at'), status=status.get('status'),
                    direction=decision.get('direction'), allowed=decision.get('allowed'),
                    entry_ready=lane.get('entry_timing_ready'), reasons=reasons,
                    positions=positions, last_execution=lane.get('last_execution'),
                    selection=decision.get('fast_timeframe_selection'),
                    candidate=decision.get('s30_entry', {}).get('fast_candidate'),
                    inverse_state=status.get('inverse', {}).get('state'))
                handle.write(json.dumps(row, default=str)+'\n')
                handle.flush()
                samples += 1
                atomic_write_json(root/'progress.json', dict(started=started.isoformat(),
                    samples=samples, last=row, top_blocks=blocks.most_common(12)))
            except Exception as error:
                errors.append(dict(at=datetime.now(timezone.utc).isoformat(), error=str(error)))
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(args.interval, remaining))
    final = broker_snapshot(started, terminal_path=args.terminal_path, expected_fingerprint=args.expected_account_fingerprint)
    report = dict(started=started.isoformat(), ended=datetime.now(timezone.utc).isoformat(),
        requested_minutes=args.minutes, samples=samples, directions=dict(directions),
        top_blocks=blocks.most_common(), observed_position_tickets=sorted(position_tickets),
        initial_broker=initial, final_broker=final, errors=errors,
        account_continuity=(initial.get('available') and final.get('available')
            and initial.get('account_fingerprint') == final.get('account_fingerprint')),
        note='Read-only observation, not calibrated signal accuracy or proof of future profitability.')
    atomic_write_json(root/'report.json', report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
