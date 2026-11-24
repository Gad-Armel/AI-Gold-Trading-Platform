"""Descriptive overlap clusters; three correlated positions are not three trials."""
from datetime import datetime
import numpy as np


def episode_audit(trades, *, cooldown_seconds=30, seed=42):
    if not trades:
        return dict(episodes=0, trades=0, mean_episode_profit=None, bootstrap_mean_interval=None)
    ordered = sorted(trades,key=lambda t:datetime.fromisoformat(t['opened_at']))
    episodes = []
    for trade in ordered:
        opened = datetime.fromisoformat(trade['opened_at']).timestamp()
        closed = datetime.fromisoformat(trade['closed_at']).timestamp()
        if closed < opened:
            raise ValueError('Trade closed before entry')
        if not episodes or opened > episodes[-1]['closed_epoch']+cooldown_seconds:
            episodes.append(dict(opened_epoch=opened,closed_epoch=closed,profit=0.,trades=0))
        episode = episodes[-1]
        episode['closed_epoch'] = max(episode['closed_epoch'],closed)
        episode['profit'] += float(trade['profit'])
        episode['trades'] += 1
    values = np.array([e['profit'] for e in episodes])
    # A conditional descriptive bootstrap, not a forecast or iid claim.
    samples = np.random.default_rng(seed).choice(values,size=(10000,len(values)),replace=True).mean(axis=1)
    low,high = np.quantile(samples,[.025,.975])
    return dict(episodes=len(episodes),trades=len(trades),
                mean_episode_profit=float(values.mean()),total_closed_profit=float(values.sum()),
                bootstrap_mean_interval=[float(low),float(high)],clusters=episodes,
                limitations=['Clusters use observed closed-trade overlap plus the analysis pause, not independent market regimes.',
                             'Still-open positions, missing fills and serial dependence can alter inference.',
                             'Bootstrap is conditional on this short sample; not a proven future-profit interval.'])
