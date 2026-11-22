"""Independent inverse demo executor on the main's hedging account."""
import argparse
import json
from pathlib import Path
import time

from config import gold_inverse_settings as cfg
from services.bot.emergency_stop import is_emergency_stop_enabled
from services.bot.scalping_instance_lock import ScalpingInstanceLock
from services.execution.gold_inverse_demo import InverseDemoExecutor
from services.research.gold_s30_execution import account_fingerprint
from services.utils.atomic_json import atomic_write_json
from services.dashboard.gold_inverse_reporting import trading_snapshot


def main_ready(now, identity):
    try:
        from datetime import datetime
        status = json.loads(Path('data/runtime/gold_consensus_status.json').read_text(encoding='utf-8'))
        age = now-datetime.fromisoformat(status['updated_at']).timestamp()
        return (status.get('mode') == 'demo' and status.get('status') == 'RUNNING'
                and status.get('account_fingerprint') == identity
                and status.get('config', {}).get('inverse_companion_supported') is True
                and 0 <= age <= 10)
    except (OSError, ValueError, TypeError, KeyError):
        return False


def main():
    if not cfg.EXECUTOR_ENABLED:
        print('Inverse executor disabled by user. Main bot only.')
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm', required=True, choices=[cfg.CONFIRMATION])
    parser.add_argument('--max-minutes', type=float, default=0.)
    args = parser.parse_args()
    if not 0 <= args.max_minutes <= 1440:
        parser.error('max-minutes must be 0..1440; 0 means until stopped')
    import MetaTrader5 as mt5
    with ScalpingInstanceLock('data/runtime/gold_inverse.lock'):
        if not mt5.initialize(timeout=10000):
            raise RuntimeError(f'MT5 unavailable: {mt5.last_error()}')
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            mt5.shutdown()
            raise RuntimeError('DEMO account required; real accounts are never allowed')
        identity = account_fingerprint(account)
        path = Path(cfg.STATE_PATH)
        state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(
            version=1, account_fingerprint=identity, links={}, bootstrapped=False)
        if (state.get('version') != 1 or state.get('account_fingerprint') != identity
                or not isinstance(state.get('links'), dict)):
            mt5.shutdown()
            raise RuntimeError('State identity mismatch or corruption; do not delete state to bypass this check')
        engine = InverseDemoExecutor(mt5, state, lambda value: atomic_write_json(cfg.STATE_PATH, value))
        report = {}
        trading = dict(available=False, reason='Waiting for broker reporting')
        last_reporting = -float('inf')
        started = time.monotonic()
        stopped = False

        def publish(status, error=''):
            payload = dict(protocol=1, state=status, heartbeat_epoch=time.time(),
                account_fingerprint=identity, magic=cfg.MAGIC, demo_only=True,
                lot=cfg.LOT, max_combined_positions=cfg.MAX_COMBINED_POSITIONS,
                signal_policy='INHERIT_MAIN_ANALYSIS_REVERSE_CONFIRMED_FILL',
                detail=report, error=error)
            payload['trading'] = trading
            atomic_write_json(cfg.STATUS_PATH, payload)

        try:
            engine.guard()
            if not main_ready(time.time(), identity):
                raise RuntimeError('Start/restart the updated main demo first; fresh companion-capable status required')
            print('Inverse DEMO running. New main fills only; no startup backfill. '
                  '0.01 lot, two inverse slots, FOUR combined positions maximum.', flush=True)
            printed = 0.
            stopping_since = None
            Path(cfg.JOURNAL_PATH).parent.mkdir(parents=True, exist_ok=True)
            while True:
                now = time.time()
                stopped = (Path(cfg.STOP_PATH).exists() or is_emergency_stop_enabled()
                    or (args.max_minutes > 0 and time.monotonic()-started >= args.max_minutes*60))
                if stopped and stopping_since is None:
                    stopping_since = time.monotonic()
                publish('STOPPING' if stopped else 'RUNNING')
                try:
                    report = engine.cycle(now, allow_new=main_ready(now, identity), stop=stopped)
                    if time.monotonic()-last_reporting >= 5:
                        try:
                            engine.guard()
                            trading = trading_snapshot(mt5)
                            engine.guard()
                        except Exception as error:
                            trading = dict(available=False, reason=str(error))
                        last_reporting = time.monotonic()
                    for event in report['events']:
                        with Path(cfg.JOURNAL_PATH).open('a', encoding='utf-8') as journal:
                            journal.write(json.dumps(dict(epoch=now, **event), allow_nan=False)+'\n')
                    publish('STOPPING' if stopped else 'RUNNING')
                    if time.monotonic()-printed >= 5:
                        print(json.dumps({key: value for key, value in report.items() if key != 'events'}), flush=True)
                        printed = time.monotonic()
                    if (stopped and not report['inverse_positions'] and report['pending_inverse_orders'] == 0
                            and not report['uncertain_links']):
                        break
                except Exception as error:
                    publish('ERROR', str(error))
                    print(f'Inverse blocked: {error}', flush=True)
                if stopping_since is not None and time.monotonic()-stopping_since >= 30:
                    break
                time.sleep(.25)
        except KeyboardInterrupt:
            stopped = True
        finally:
            remaining = None
            try:
                engine.cycle(time.time(), allow_new=False, stop=True)
                remaining = sum(position.magic == cfg.MAGIC for position in engine.positions())
                pending = mt5.orders_get(symbol=cfg.SYMBOL)
                if pending is None or any(order.magic == cfg.MAGIC for order in pending):
                    remaining = None
                if any(link.get('open') in ('INTENT', 'UNCERTAIN') or link.get('close') in ('INTENT', 'UNCERTAIN')
                       for link in state['links'].values()):
                    remaining = None
            except Exception as error:
                report['shutdown_error'] = str(error)
            publish('STOPPED' if remaining == 0 else 'STOPPED_WITH_UNRESOLVED_POSITIONS',
                    '' if remaining == 0 else 'Check inverse positions in MT5; protective SLs remain')
            mt5.shutdown()


if __name__ == '__main__':
    main()
