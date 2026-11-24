"""Summarize all recorded paper sessions without discarding losing runs."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    rows = []
    for path in sorted((ROOT/'data/research/gold_paper').glob('*/account.json')):
        account = json.loads(path.read_text(encoding='utf-8'))
        journal = path.parent/'trades.jsonl'
        trades = [json.loads(line) for line in journal.read_text(encoding='utf-8').splitlines() if line] if journal.exists() else []
        gains = sum(t['profit'] for t in trades if t['profit'] > 0)
        losses = -sum(t['profit'] for t in trades if t['profit'] < 0)
        rows.append(dict(run_id=account['run_id'], learned_policy=account.get('learned_policy'),
                         cross_market_policy=account.get('cross_market_policy', 'observe'),
                         trades=len(trades), balance=account['balance'], equity=account['equity'],
                         max_drawdown_usd=account['max_drawdown_usd'],
                         profit_factor=gains/losses if losses else None,
                         accounting_reconciled=abs(100+gains-losses-account['balance']) < .000001,
                         open_positions=len(account['positions'])))
    report = dict(sessions=rows, note='Separate $100 paper sessions, not independent experiments or guaranteed broker fills')
    target = ROOT/'data/research/gold_ai/forward_summary.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if all(row['accounting_reconciled'] for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
