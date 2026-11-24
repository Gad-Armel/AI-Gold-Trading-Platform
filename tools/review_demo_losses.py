"""Read-only demo-history audit joined to recorded entry signals; never sends orders."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import gold_consensus_settings as settings
from services.execution.gold_consensus_demo_broker import recent_closed_consensus_trades


def metrics(rows):
    values = [float(row['profit']) for row in rows]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gains, lost = sum(wins), -sum(losses)
    return dict(trades=len(values), net=round(sum(values), 2), wins=len(wins), losses=len(losses),
                average_win=round(gains/len(wins), 4) if wins else None,
                average_loss=round(-lost/len(losses), 4) if losses else None,
                expectancy=round(sum(values)/len(values), 4) if values else None,
                profit_factor=round(gains/lost, 4) if lost else None)


def trade_cohort(trades, since):
    start = datetime.fromisoformat(since.replace('Z', '+00:00'))
    if start.tzinfo is None:
        raise ValueError('Cohort start requires an explicit timezone')
    return [trade for trade in trades if datetime.fromisoformat(trade['opened_at']) >= start]


def group_metrics(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[str(key(row))].append(row)
    return {name: metrics(group) for name, group in sorted(groups.items())}


def exit_family(row):
    reason = str(row.get('exit_reason') or 'UNKNOWN')
    for prefix in ('Flow reversal risk', 'Profit giveback', 'Profit lock', 'Sustained executable quote reversal'):
        if reason.startswith(prefix):
            return prefix
    return 'Broker stop loss' if reason.startswith('[sl ') else reason


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days', type=int, default=14)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--since', help='ISO time with timezone; separate cohort by entry time, not exit time')
    args = parser.parse_args()
    import MetaTrader5 as mt5
    if not mt5.initialize(timeout=10000):
        raise RuntimeError(str(mt5.last_error()))
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError('Verified demo account required')
        trades = []
        for name, config in settings.HORIZON_LANES.items():
            trades.extend(dict(item, horizon=name) for item in recent_closed_consensus_trades(
                mt5, limit=10000, lookback_days=args.days, magic_number=int(config['magic']), strict=True))
    finally:
        mt5.shutdown()
    entries = {}
    closes = {}
    journal = ROOT / settings.JOURNAL_PATH
    if journal.exists():
        with journal.open(encoding='utf-8') as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if item.get('record_type') == 'HORIZON_OPEN' and item.get('success'):
                    entries[str(item.get('order'))] = item
                elif item.get('record_type') == 'CLOSE' and item.get('success'):
                    closes[str(item.get('position_ticket'))] = item
    for trade in trades:
        opened = entries.get(str(trade['position_id']), {})
        decision = opened.get('entry_context', {}).get('decision', {})
        trade.update(evidence=opened.get('evidence'), entry_mode=decision.get('entry_mode', 'NOT_RECORDED'),
                     quote_age=opened.get('entry_context', {}).get('quote', {}).get('age_seconds'),
                     exit_reason=closes.get(str(trade['position_id']), {}).get('reason', trade.get('close_comment')),
                     setup_available=decision.get('setup_observation', {}).get('available'),
                     entry_contributors=decision.get('contributors', []))
    trades.sort(key=lambda row: row['opened_at'])
    scalp = [row for row in trades if row['horizon'] == 'SCALP']
    matched = [row for row in scalp if isinstance(row['evidence'], (int, float))]
    report = dict(as_of=datetime.now(timezone.utc).isoformat(), read_only=True, lookback_days=args.days,
                  overall=metrics(trades), by_lane=group_metrics(trades, lambda row: row['horizon']),
                  scalp_by_day=group_metrics(scalp, lambda row: row['opened_at'][:10]),
                  scalp_by_direction=group_metrics(scalp, lambda row: row['direction']),
                  scalp_by_exit_reason=group_metrics(scalp, exit_family),
                  scalp_recorded_evidence=group_metrics(matched, lambda row: '85_or_more' if row['evidence'] >= 85 else 'below_85'),
                  recent_scalp=metrics(scalp[-30:]), recent_trades=scalp[-30:],
                  limitations=['Historical policies are mixed unless explicitly stratified by cohort.',
                               'Signal evidence is heuristic, not a probability; this audit does not select a profitable threshold.',
                               'Journal/order joins can be missing. Broker net P/L includes available position fees.',
                               'Only fully closed positions with recoverable opening deals in the requested window are included.'])
    if args.since:
        cohort = trade_cohort(scalp, args.since)
        report['requested_scalp_cohort'] = dict(opened_on_or_after=args.since, metrics=metrics(cohort), trades=cohort)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in ('recent_trades',)}, indent=2))


if __name__ == '__main__':
    main()
