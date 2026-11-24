"""Small account-bound command mailbox. MT5 alone applies commands and trades."""
from __future__ import annotations

import os
from pathlib import Path
import re
import threading
import time
import uuid


class ControlConflict(ValueError):
    pass


class ControlMailbox:
    def __init__(self, directory: Path):
        self.directory = directory
        self.lock = threading.Lock()
        self.pending: dict[str, tuple[str, int]] = {}

    def enqueue(self, payload: dict, status: dict, now: float | None = None) -> dict:
        now = int(time.time() if now is None else now)
        if not isinstance(payload, dict) or set(payload) != {'source', 'instance', 'action'}:
            raise ValueError('Expected source, instance and action')
        action, source, instance = payload['action'], payload['source'], payload['instance']
        if action not in ('pause', 'resume', 'close_all', 'reset_session'):
            raise ValueError('Unsupported control action')
        if not isinstance(source, str) or not re.fullmatch(r'dashboard_[A-Za-z0-9_]+\.json', source):
            raise ValueError('Invalid account feed')
        if not isinstance(instance, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,100}', instance):
            raise ValueError('Invalid EA instance')
        snapshot = status.get('snapshot') or {}
        controls = snapshot.get('controls') or {}
        if (status.get('state') != 'live' or status.get('source') != source or
                controls.get('instance') != instance or controls.get('enabled') is not True):
            raise ControlConflict('EA is stale, disconnected, changed, or browser controls are disabled')
        if action == 'reset_session' and controls.get('can_reset') is not True:
            raise ControlConflict('Reset requires a fresh supported EA, flat account and no pending requests')
        if action == 'resume' and (snapshot.get('locked') or controls.get('liquidating')):
            raise ControlConflict('Resume is blocked by safety lock or ongoing liquidation')
        if action == 'close_all' and controls.get('can_execute') is not True:
            raise ControlConflict('MT5 demo execution must be enabled to close positions')
        target = self.directory / ('control_' + source[len('dashboard_'):-len('.json')] + '.csv')
        with self.lock:
            queued = self.pending.get(source)
            if queued and now <= queued[1] and controls.get('last_id') != queued[0]:
                raise ControlConflict('Waiting for MT5 acknowledgement of the previous command')
            if target.exists():
                # An expired mailbox may remain if the EA stopped. Do not overwrite a live command.
                if now - target.stat().st_mtime <= 12:
                    raise ControlConflict('A command is already pending in MT5')
                target.unlink()
            command_id, expires = uuid.uuid4().hex, now + 10
            line = f'GOLD_CONTROL_V1;{instance};{command_id};{now};{expires};{action};END\n'
            temporary = target.with_suffix('.' + command_id + '.tmp')
            try:
                temporary.write_text(line, encoding='ascii')
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
            self.pending[source] = (command_id, expires)
            return dict(id=command_id, expires=expires, state='queued', action=action,
                        message='Queued for MT5. This is not an execution acknowledgement.')
