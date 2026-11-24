"""Display-only P/L/history baseline. Never changes execution risk state."""
import json
import time
from pathlib import Path
from services.utils.atomic_json import atomic_write_json

RESET_PATH = Path('data/runtime/gold_dual_display_reset.json')


def load_display_reset(identity):
    try:
        value = json.loads(RESET_PATH.read_text(encoding='utf-8'))
        if value.get('account_fingerprint') == identity:
            return value
    except (OSError, ValueError, TypeError):
        pass
    return None


def reset_both_displays(status, *, now=None):
    inverse = status.get('inverse', {})
    report = inverse.get('trading', {})
    if not inverse.get('fresh') or not report.get('available') or not status.get('account_fingerprint'):
        raise ValueError('Wait for fresh broker reporting from both bots before resetting')
    main = report.get('main_display', {})
    if not main.get('pnl', {}).get('available') or not report.get('pnl', {}).get('available'):
        raise ValueError('Both broker P/L panels must be available')
    baseline = dict(reset_epoch=time.time() if now is None else now,
        account_fingerprint=status['account_fingerprint'],
        main_open_baseline=main['pnl'].get('actual_floating', main['pnl']['floating']),
        inverse_open_baseline=report['pnl'].get('actual_floating', report['pnl']['floating']),
        paired_main_open_baseline=report.get('paired', {}).get('main_actual_floating', 0.),
        scope='Display only; broker history, positions and risk controls unchanged')
    atomic_write_json(RESET_PATH, baseline)
    return dict(success=True, **baseline)
