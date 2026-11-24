"""Require fresh confirmation for each entry; never authorizes orders or changes exits."""
from config import gold_consensus_settings as settings
import math


def staged_confirmation(positions):
    epochs = [position.get('opened_epoch') for position in positions]
    valid = all(isinstance(epoch, (int, float)) and not isinstance(epoch, bool)
                and math.isfinite(epoch) and epoch > 0 for epoch in epochs)
    return dict(required_bars=settings.SCALP_M1_CONFIRMATION_BARS,
                after_epoch=max(epochs) if epochs and valid else 0 if epochs else None)


def execution_confirmation(plan, *, scalp=True):
    if scalp and settings.SCALP_STAGED_M1_ENABLED is True:
        return plan
    return dict(required_bars=settings.SCALP_M1_CONFIRMATION_BARS if scalp else 1, after_epoch=None)


def fast_confirmation(plan):
    count = plan['required_bars']
    if isinstance(count, bool) or count not in (1, 2, 3, 5, 6):
        raise ValueError('Unsupported fast confirmation plan')
    return dict(plan, required_bars=max(settings.FAST_CONFIRMATION_BARS, count))
