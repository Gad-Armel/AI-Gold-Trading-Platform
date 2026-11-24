"""Read-only historical eligibility counts for the actual fast demo entry gates."""
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import gold_consensus_settings as settings
from services.research.gold_s30_execution import load_costs, entry_check
from services.research.gold_tick_history import TickHistoryBuffer
from services.utils.atomic_json import atomic_write_json


def main():
    import MetaTrader5 as mt5
    if not mt5.initialize(timeout=10000):
        raise RuntimeError('MT5 initialization failed')
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError('Verified demo required')
        now = datetime.now(timezone.utc)
        path = ROOT/'data/runtime/s5_provisional_demo_costs.json'
        costs = load_costs(path, now=now.timestamp(), allow_provisional=True, account=account)
        frame, health = TickHistoryBuffer().refresh(mt5, settings.SYMBOL, now)
        if not health['available']:
            raise RuntimeError(health['error'])
        ticks = frame[['timestamp', 'bid', 'ask']].to_dict('records')
        stamps = [tick['timestamp'] for tick in ticks]
        summary = {}
        for period in (5, 15, 30):
            counts, blockers, setups = Counter(), Counter(), set()
            for epoch in range(int(stamps[0])+121, int(now.timestamp())):
                window = ticks[bisect_left(stamps, epoch-120):bisect_right(stamps, epoch)]
                blocks, report = entry_check(dict(direction='WAIT'), window, now=epoch,
                    plan=dict(required_bars=3, after_epoch=None), cost_path=path,
                    period_seconds=period, allow_provisional=True, account=account)
                blocks = [reason for reason in blocks if 'confirmation must agree' not in reason]
                counts['evaluated_seconds'] += 1
                if report.get('direction') in ('BUY', 'SELL'):
                    counts['directional_seconds'] += 1
                for reason in blocks:
                    blockers[reason] += 1
                if not blocks:
                    counts['gate_pass_seconds'] += 1
                    setups.add(report['fast_candidate']['setup_id'])
            summary[f'S{period}'] = dict(counts=dict(counts), distinct_candidate_setups=len(setups),
                                         blocker_counts=dict(blockers))
        result = dict(as_of=now.isoformat(), read_only=True, costs=costs, summary=summary,
            limitations=['Eligibility counts only, not profitability or a portfolio backtest.',
                          'Does not replay news, broker sends, evidence threshold, persistence or latency.',
                          'Signal overlap and per-second counts are not independent trades.'])
        output = ROOT/'data/research/goldhft_20261020/auto_eligibility_latest.json'
        atomic_write_json(str(output), result, indent=2)
        print(json.dumps(result, indent=2))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
