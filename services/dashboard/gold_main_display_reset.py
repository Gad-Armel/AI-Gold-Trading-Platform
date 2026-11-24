"""Account-bound display baseline; never changes broker or trading risk state."""
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from services.utils.atomic_json import atomic_write_json

PATH = Path('data/runtime/gold_main_display_reset.json')


def reset_main_display(status, *, now=None):
    pnl = status.get('broker_pnl', status.get('pnl', {}))
    identity = status.get('account_fingerprint')
    stamp = datetime.fromisoformat(status['updated_at']).timestamp()
    now = time.time() if now is None else now
    if not identity or not pnl.get('available') or not 0 <= now-stamp <= 15:
        raise ValueError('Fresh broker reporting is required before resetting the display')
    value = dict(account_fingerprint=identity, reset_epoch=now,
                 realized=float(pnl['realized']), floating=float(pnl['floating']))
    atomic_write_json(PATH, value)
    return dict(success=True, **value)


def apply_main_display_reset(status):
    pnl = dict(status.get('pnl', {}))
    status['broker_pnl'] = pnl
    try:
        baseline = json.loads(PATH.read_text(encoding='utf-8'))
        if baseline['account_fingerprint'] != status.get('account_fingerprint'):
            return status
        cutoff = float(baseline['reset_epoch'])
        if pnl.get('available'):
            realized = float(pnl['realized'])-float(baseline['realized'])
            floating = float(pnl['floating'])-float(baseline['floating'])
            status['pnl'] = dict(pnl, realized=realized, floating=floating,
                                 total=realized+floating, actual_floating=pnl['floating'])
        for lane in status.get('lanes', {}).values():
            lane['closed_trades'] = [row for row in lane.get('closed_trades', [])
                if datetime.fromisoformat(row['closed_at']).timestamp() > cutoff]
        status['display_scope'] = 'Display change since '+datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
        status['display_reset_at'] = cutoff
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return status
