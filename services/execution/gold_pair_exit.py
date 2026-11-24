"""Account-bound close decisions shared with the separate inverse executor."""
import json
import time
from pathlib import Path

from services.research.gold_s30_execution import account_fingerprint
from services.utils.atomic_json import atomic_write_json

ROOT = Path('data/runtime/gold_pair_exits')


def publish_exit(mt5, position, reason):
    identity = account_fingerprint(mt5.account_info())
    source = str(getattr(position, 'identifier', 0) or position.ticket)
    ROOT.mkdir(parents=True, exist_ok=True)
    atomic_write_json(ROOT / (source + '.json'), dict(
        account_fingerprint=identity, source_id=source, decided_at=time.time(), reason=reason))


def exit_requested(source, identity):
    if not str(source).isdigit():
        return False
    try:
        value = json.loads((ROOT / (str(source) + '.json')).read_text(encoding='utf-8'))
        return (isinstance(value, dict) and value.get('account_fingerprint') == identity
                and value.get('source_id') == str(source))
    except (OSError, ValueError, TypeError):
        return False
