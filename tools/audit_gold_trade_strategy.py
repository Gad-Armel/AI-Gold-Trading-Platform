"""Reconcile closed demo positions with entry journal context; never sends orders."""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def summarize(rows):
    wins = [row['net'] for row in rows if row['net'] > 0]
    losses = [row['net'] for row in rows if row['net'] < 0]
    return dict(trades=len(rows), net=round(sum(row['net'] for row in rows), 4),
        wins=len(wins), losses=len(losses), win_rate=len(wins)/len(rows) if rows else None,
        average_win=sum(wins)/len(wins) if wins else None,
        average_loss=sum(losses)/len(losses) if losses else None,
        profit_factor=sum(wins)/-sum(losses) if losses else None)


def analyze(deals, journal, *, offset=10800):
    unique = {int(row['ticket']): row for row in deals}
    groups = defaultdict(list)
    for row in unique.values():
        if row.get('symbol') == 'XAUUSD' and row.get('type') in (0, 1):
            groups[row['position_id']].append(row)
    entries = {int(row.get('deal') or 0): row for row in journal
               if row.get('record_type') == 'HORIZON_OPEN' and row.get('success')}
    closes = {int(row.get('deal') or 0): row for row in journal if row.get('record_type') == 'CLOSE'}
    rows, excluded = [], defaultdict(int)
    for position_id, group in groups.items():
        opened = [row for row in group if row.get('entry') == 0 and row.get('magic') == 631011]
        if not opened:
            continue
        exited = [row for row in group if row.get('entry') in (1, 3)]
        incoming = sum(row['volume'] for row in opened)
        outgoing = sum(row['volume'] for row in exited)
        if any(row.get('entry') == 2 for row in group) or abs(incoming-outgoing) > 1e-8:
            excluded['open_partial_or_reversal'] += 1
            continue
        if not exited:
            excluded['unclosed'] += 1
            continue
        entry = min(opened, key=lambda row: row['time_msc'])
        last = max(exited, key=lambda row: row['time_msc'])
        record = entries.get(entry['ticket'], {})
        decision = record.get('entry_context', {}).get('decision', {})
        observation = decision.get('entry_observation', {})
        micro = observation.get('micro_flow', {})
        warnings = decision.get('s30_entry', {}).get('fast_candidate', {}).get('warnings', [])
        fast = decision.get('s30_entry', {}).get('fast_candidate', {})
        micro_passed = (fast.get('signed_move_price', 0.) > fast.get('spread_price', float('inf'))
                        and fast.get('quote_efficiency', 0.) >= .65) if fast else None
        stop = record.get('sl')
        entry_price = sum(row['price']*row['volume'] for row in opened)/incoming
        rows.append(dict(position_id=position_id, entry_deal=entry['ticket'], entry_price=entry_price,
            volume=incoming, net=sum(sum(row.get(key, 0.) for key in
            ('profit', 'commission', 'swap', 'fee')) for row in group),
            opened_utc=datetime.fromtimestamp(entry['time_msc']/1000-offset, timezone.utc).isoformat(),
            closed_utc=datetime.fromtimestamp(last['time_msc']/1000-offset, timezone.utc).isoformat(),
            hold_seconds=(last['time_msc']-entry['time_msc'])/1000,
            timeframe=decision.get('entry_timeframe', 'UNKNOWN'), matched_entry=bool(record),
            evidence=record.get('evidence'), direction='BUY' if entry['type'] == 0 else 'SELL',
            initial_stop_distance=abs(entry_price-stop) if stop else None,
            higher_timeframe_alignment=decision.get('higher_timeframe_context', {}).get('alignment'),
            micro_efficiency=micro.get('efficiency'), micro_pressure=micro.get('pressure'),
            warning_count=len(warnings), micro_confirmation_passed=micro_passed,
            close_comment=last.get('comment', ''),
            exit_reason=closes.get(last['ticket'], {}).get('reason', last.get('comment', ''))))
    rows.sort(key=lambda row: row['closed_utc'])
    by_timeframe = {key: summarize([row for row in rows if row['timeframe'] == key])
                    for key in sorted({row['timeframe'] for row in rows})}
    by_alignment = {key: summarize([row for row in rows if
        ('UNKNOWN' if row['higher_timeframe_alignment'] is None else 'OPPOSED'
         if row['higher_timeframe_alignment'] < 0 else 'ALIGNED_OR_NEUTRAL') == key])
        for key in ('OPPOSED', 'ALIGNED_OR_NEUTRAL', 'UNKNOWN')}
    by_exit = {key: summarize([row for row in rows if row['exit_reason'] == key])
               for key in sorted({row['exit_reason'] for row in rows})}
    by_micro_confirmation = {key: summarize([row for row in rows if
        ('UNKNOWN' if row['micro_confirmation_passed'] is None else 'PASS'
         if row['micro_confirmation_passed'] else 'FAIL') == key]) for key in ('PASS', 'FAIL', 'UNKNOWN')}
    return dict(summary=summarize(rows), by_timeframe=by_timeframe, by_alignment=by_alignment,
                by_exit=by_exit, by_micro_confirmation=by_micro_confirmation,
                excluded=dict(excluded), closed_positions=rows,
                limitations=['Retrospective grouped associations are not causal strategy tests.',
                    'Unclosed/partial/reversal and entries outside this history window are excluded.',
                    'No confidence interval or positive expectancy inferred from these groups.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hours', type=float, default=24.)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--terminal-path')
    parser.add_argument('--expected-account-fingerprint')
    args = parser.parse_args()
    if not 0 < args.hours <= 168:
        parser.error('hours must be in (0,168]')
    import MetaTrader5 as mt5
    from config import gold_consensus_settings as settings
    from services.market_data.gold_broker_clock import to_broker_time
    from services.research.gold_s30_execution import account_fingerprint
    if not mt5.initialize(*([args.terminal_path] if args.terminal_path else []), timeout=10000):
        raise RuntimeError(mt5.last_error())
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError('Verified demo required')
        if args.expected_account_fingerprint and account_fingerprint(account)!=args.expected_account_fingerprint:
            raise RuntimeError('Audit account differs from approved demo identity')
        now = datetime.now(timezone.utc)
        deals = mt5.history_deals_get(to_broker_time(now-timedelta(hours=args.hours)), to_broker_time(now))
        if deals is None:
            raise RuntimeError(mt5.last_error())
        journal, malformed = [], 0
        with Path(settings.JOURNAL_PATH).open(encoding='utf-8') as source:
            for line in source:
                try:
                    journal.append(json.loads(line))
                except json.JSONDecodeError:
                    malformed += 1
        report = analyze([row._asdict() for row in deals], journal,
                         offset=settings.MT5_SERVER_UTC_OFFSET_SECONDS)
        report.update(as_of=now.isoformat(), requested_hours=args.hours, currency=account.currency,
            account_fingerprint=account_fingerprint(account), read_only=True, malformed_journal_lines=malformed)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
        print(json.dumps({key: report[key] for key in ('summary', 'by_timeframe', 'by_alignment', 'by_micro_confirmation')}, indent=2))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
