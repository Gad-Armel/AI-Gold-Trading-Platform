"""Create an explicitly assumed cost profile bound to the connected demo; no orders."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.research.gold_s30_execution import account_fingerprint
from services.utils.atomic_json import atomic_write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--terminal-path')
    parser.add_argument('--expected-account-fingerprint', help='Refuse renewal on a different account')
    args = parser.parse_args()
    import MetaTrader5 as mt5
    if not mt5.initialize(*([args.terminal_path] if args.terminal_path else []), timeout=10000):
        raise RuntimeError('MT5 initialization failed')
    try:
        account, terminal, info = mt5.account_info(), mt5.terminal_info(), mt5.symbol_info('XAUUSD')
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO or account.currency != 'USD':
            raise RuntimeError('Connected USD demo required')
        if args.expected_account_fingerprint and account_fingerprint(account) != args.expected_account_fingerprint:
            raise RuntimeError('Connected demo differs from the approved renewal identity')
        if terminal is None or not terminal.connected or not terminal.trade_allowed:
            raise RuntimeError('Connected terminal with Algo Trading enabled required')
        if info is None or info.trade_contract_size != 100 or info.volume_min > .01:
            raise RuntimeError('XAUUSD 100oz contract with 0.01 lot required')
        profile = dict(as_of=datetime.now(timezone.utc).isoformat(), profile_type='PROVISIONAL_DEMO',
            account_fingerprint=account_fingerprint(account),
            terminal_path=str(Path(terminal.path)/'terminal64.exe'), read_only=True, symbol='XAUUSD',
            currency='USD', volume=.01, costs=dict(available=False, reconciled_pairs=0,
            commission_price=.10, slippage_price=.20),
            warning='User-approved demo assumptions, NOT measurements or guaranteed maximum costs. Spread is live and added separately.')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(str(args.output), profile, indent=2)
        print('Account-bound PROVISIONAL_DEMO profile created. Commission 0.10 + slippage 0.20, round-trip XAUUSD price equivalents; live spread additional. No orders sent.')
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
