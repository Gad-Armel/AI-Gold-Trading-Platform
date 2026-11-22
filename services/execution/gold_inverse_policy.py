"""Account-bound heartbeat used only for cooperative demo capacity allocation."""
import json
import time
from pathlib import Path

from config import gold_inverse_settings as inverse
from services.research.gold_s30_execution import account_fingerprint


def inverse_active(account, *, now=None):
    if account is None or getattr(account, 'trade_mode', -1) != 0:
        return False
    now = time.time() if now is None else now
    try:
        status = json.loads(Path(inverse.STATUS_PATH).read_text(encoding='utf-8'))
        return (status.get('protocol') == 1 and status.get('state') == 'RUNNING'
                and status.get('magic') == inverse.MAGIC
                and status.get('account_fingerprint') == account_fingerprint(account)
                and 0 <= now-float(status['heartbeat_epoch']) <= 15)
    except (OSError, ValueError, KeyError, TypeError):
        return False
