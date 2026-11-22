"""Compare raw-tick and one-second S30 efficiency gates without sending orders."""
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import gold_consensus_settings as settings
from services.research.gold_s30_execution import load_costs
from services.research.gold_s30_shadow import s30_observation
from services.research.gold_tick_history import TickHistoryBuffer
from services.utils.atomic_json import atomic_write_json


def main():
    import MetaTrader5 as mt5
    if not mt5.initialize(timeout=10000):
        raise RuntimeError('MT5 initialization failed')
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError('Verified demo account required')
        now = datetime.now(timezone.utc)
        costs = load_costs(ROOT/'data/research/goldhft_20261020/s30_execution_costs.json', now=now.timestamp())
        frame, health = TickHistoryBuffer().refresh(mt5, settings.SYMBOL, now)
        if not health['available']:
            raise RuntimeError(health['error'])
        ticks = frame[['timestamp', 'bid', 'ask']].to_dict('records')
        stamps = [tick['timestamp'] for tick in ticks]
        counts, blocks = Counter(), Counter()
        old_setups, new_setups = set(), set()
        for epoch in range(int(stamps[0])+121, int(now.timestamp())):
            window = ticks[bisect_left(stamps, epoch-120):bisect_right(stamps, epoch)]
            observation = s30_observation(window, now=epoch, commission_price=costs['commission_price'],
                                          slippage_price=costs['slippage_price'])
            fast = observation.get('fast_candidate', {})
            counts['evaluated_seconds'] += 1
            counts['three_directional_S30_seconds'] += observation.get('direction') in ('BUY', 'SELL')
            for block in fast.get('blocks', []):
                blocks[block] += 1
            if fast.get('research_candidate'):
                counts['one_second_gate_pass_seconds'] += 1
                new_setups.add(fast['setup_id'])
                if fast['raw_tick_efficiency'] >= .65:
                    counts['raw_tick_gate_pass_seconds'] += 1
                    old_setups.add(fast['setup_id'])
        report = dict(as_of=now.isoformat(), read_only=True, execution_enabled=False,
                      counts=dict(counts), blockers=dict(blocks), old_candidate_setups=len(old_setups),
                      corrected_candidate_setups=len(new_setups),
                      limitation='Candidate-gate diagnostic only; not portfolio execution or profitability evidence.')
        output = ROOT/'data/research/goldhft_20261020/efficiency_diagnostic.json'
        atomic_write_json(str(output), report, indent=2)
        print(json.dumps(report, indent=2))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
