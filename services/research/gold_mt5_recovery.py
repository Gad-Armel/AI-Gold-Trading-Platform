"""Bounded main-only IPC recovery, pinned to the original demo identity."""
import math


class Mt5Recovery:
    def __init__(self, account):
        self.identity = self._identity(account)
        if not self.identity[0] or not self.identity[1] or self.identity[2] != 0:
            raise ValueError('Verified demo identity required for recovery')
        self.last_attempt = -float('inf')

    @staticmethod
    def _identity(account):
        return (getattr(account, 'login', None), getattr(account, 'server', None),
                getattr(account, 'trade_mode', None))

    def attempt(self, mt5, *, now):
        if not math.isfinite(now) or now-self.last_attempt < 15:
            return dict(attempted=False, reconnected=False)
        self.last_attempt = now
        try:
            mt5.shutdown()
            if not mt5.initialize(timeout=2000):
                return dict(attempted=True, reconnected=False, reason='MT5 IPC initialization failed')
            if self._identity(mt5.account_info()) != self.identity:
                return dict(attempted=True, reconnected=False, reason='Account identity changed; recovery blocked')
            terminal = mt5.terminal_info()
            if terminal is None or not terminal.connected:
                return dict(attempted=True, reconnected=False, reason='MT5 broker connection unavailable')
            return dict(attempted=True, reconnected=True, reason='MT5 IPC reconnected; fresh snapshot required')
        except Exception as error:
            return dict(attempted=True, reconnected=False, reason=f'MT5 recovery failed: {type(error).__name__}')
