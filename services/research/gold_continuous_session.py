"""Loss policy and nonblocking post-exit analysis for the main demo bot."""
from config import gold_consensus_settings as settings


def session_loss_stop(pnl):
    if not settings.SESSION_LOSS_STOP_ENABLED or not pnl.get('available'):
        return False
    limit = getattr(settings, 'MAX_SESSION_LOSS_USD', None)
    if limit is None:
        return False
    total = float(pnl.get('total', 0))
    # The legacy -100 test is a stress sentinel, not a valid configured
    # five-dollar session threshold. Only configured losses produce a stop.
    return -100.0 < total <= -float(limit)


def post_exit_blocks(states, *, now):
    last_exit = max((state.get('last_exit_at', -float('inf')) for state in states.values()),
                    default=-float('inf'))
    duration = float(settings.POST_EXIT_ANALYSIS_SECONDS)
    if len(states) > 1 or any(isinstance(state.get('candle_confirmation_state'), dict)
                              and state['candle_confirmation_state'] for state in states.values()):
        duration = 30.0
    remaining = duration - (now-last_exit)
    return [f'Post-exit market analysis: {remaining:.0f}s remaining.'] if remaining > 0 else []
