"""Account-bound adaptive state; never restore stale confirmation evidence."""
import hashlib
import json
import math
from pathlib import Path

from config import gold_consensus_settings as settings
from services.utils.atomic_json import atomic_write_json


class GoldExitStateStore:
    def __init__(self, path, account):
        self.path = Path(path)
        if account is None or not getattr(account, 'login', None) or not getattr(account, 'server', None):
            raise ValueError('Account identity required for exit state')
        identity = dict(login=account.login, server=account.server, mode=account.trade_mode,
                        symbol=settings.SYMBOL, lanes=settings.HORIZON_LANES,
                        exit_policy=settings.ADAPTIVE_EXIT_CONFIG)
        self.identity = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        self.status = 'NEW'

    @staticmethod
    def _number(value):
        return isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value)

    def load(self, now):
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data['version'] != 1 or data['identity'] != self.identity:
                raise ValueError('Identity or policy changed')
            saved_at = data['saved_at']
            if not self._number(saved_at) or not 0 <= now-saved_at <= 7*86400:
                raise ValueError('State timestamp outside recovery window')
            restored = {}
            for name, lane in data['lanes'].items():
                if name not in settings.HORIZON_LANES or not isinstance(lane,dict):
                    raise ValueError('Invalid lane')
                exit_state = lane['exit_state']
                if not isinstance(exit_state,dict):
                    raise ValueError('Invalid exit state')
                if exit_state:
                    for key in ('started','peak_move','trough_move'):
                        if not self._number(exit_state.get(key)):
                            raise ValueError('Invalid excursion state')
                    if not 0 <= exit_state['started'] <= saved_at or exit_state['trough_move'] > exit_state['peak_move']:
                        raise ValueError('Invalid state ordering')
                    signature = exit_state.get('position_signature')
                    if not isinstance(signature,list) or not 1 <= len(signature) <= max(c['max_positions'] for c in settings.HORIZON_LANES.values()):
                        raise ValueError('Invalid position binding')
                    for p in signature:
                        if (not isinstance(p,list) or len(p)!=4 or not isinstance(p[0],int) or p[0]<=0
                                or p[1] not in ('BUY','SELL') or not all(self._number(v) and v>0 for v in p[2:])):
                            raise ValueError('Invalid position binding')
                    peaks = exit_state.get('ticket_profit_peaks', {})
                    if (not isinstance(peaks, dict) or any(
                            key not in {str(p[0]) for p in signature} or not self._number(value)
                            for key, value in peaks.items())):
                        raise ValueError('Invalid per-position profit peaks')
                    # Time offline must never count as sustained adverse evidence,
                    # for the thesis timer or for the conscience collapse timer.
                    exit_state['adverse_since'] = None
                    exit_state.pop('conscience_state', None)
                    risk = exit_state.get('initial_risk_price')
                    if risk is not None and (not self._number(risk) or risk <= 0):
                        raise ValueError('Invalid initial risk distance')
                previous = lane['previous_tickets']
                if not isinstance(previous,list) or any(not isinstance(t,int) or t<=0 for t in previous):
                    raise ValueError('Invalid previous positions')
                bar = lane['last_closed_bar']
                if bar is not None and (not isinstance(bar,str) or len(bar)>80):
                    raise ValueError('Invalid re-entry marker')
                restored[name] = dict(exit_state=exit_state, previous_tickets=previous,last_closed_bar=bar)
                period = lane.get('entry_period_seconds')
                if period is not None:
                    if isinstance(period, bool) or period not in (1, 5, 15, 30):
                        raise ValueError('Invalid entry timeframe')
                    restored[name]['entry_period_seconds'] = period
                last_exit = lane.get('last_exit_at')
                if last_exit is not None and (not self._number(last_exit) or not 0 <= last_exit <= saved_at):
                    raise ValueError('Invalid post-exit cooldown timestamp')
                # Older snapshots do not carry cooldown state: warm up rather
                # than allowing a restart to skip the post-exit analysis pause.
                restored[name]['last_exit_at'] = last_exit if last_exit is not None else now
                exit_direction = lane.get('last_exit_direction')
                if exit_direction not in (None, 'BUY', 'SELL'):
                    raise ValueError('Invalid last exit direction')
                restored[name]['last_exit_direction'] = exit_direction
                confirmation = lane.get('candle_confirmation_state', {})
                if not isinstance(confirmation, dict):
                    raise ValueError('Invalid candle confirmation state')
                if confirmation:
                    peak = confirmation.get('peak')
                    waiting = confirmation.get('waiting_since')
                    if (not self._number(peak) or not 0 <= peak <= 100
                            or confirmation.get('direction') not in ('BUY', 'SELL', 'WAIT')
                            or (waiting is not None and (not self._number(waiting) or not 0 <= waiting <= saved_at))):
                        raise ValueError('Invalid candle confirmation evidence')
                    restored[name]['candle_confirmation_state'] = dict(
                        direction=confirmation['direction'], peak=peak, waiting_since=waiting)
            self.status = 'RESTORED'
            return restored
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            self.status = 'REJECTED_INVALID_OR_MISMATCHED_STATE'
            return {}

    def save(self, states, now):
        lanes = {name:{key:lane[key] for key in ('exit_state','previous_tickets','last_closed_bar')}
                 for name,lane in states.items()}
        for name, lane in states.items():
            last_exit = lane.get('last_exit_at')
            lanes[name]['last_exit_at'] = last_exit if self._number(last_exit) else None
            lanes[name]['last_exit_direction'] = lane.get('last_exit_direction')
            lanes[name]['candle_confirmation_state'] = lane.get('candle_confirmation_state', {})
            lanes[name]['entry_period_seconds'] = lane.get('entry_period_seconds')
        atomic_write_json(self.path,dict(version=1,identity=self.identity,saved_at=now,lanes=lanes),
                          replace_retries=2,retry_delay_seconds=.01)
