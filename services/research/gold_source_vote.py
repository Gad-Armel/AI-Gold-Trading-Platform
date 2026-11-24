"""User-requested source-count allocation; strength scores are not probabilities."""
import math
from datetime import datetime

SOURCES = ('MT5_CANDLES', 'API_CANDLES', 'MT5_TICK_FLOW')


def source_vote(decision, context, *, now, threshold=75., maximum=3):
    contributors = [dict(c) for c in decision.get('contributors', []) if c.get('advisor') in SOURCES]
    votes = {'BUY': [], 'SELL': []}
    seen = set()
    for c in contributors:
        name = c['advisor']
        if name in seen:
            continue
        seen.add(name)
        try:
            score = float(c.get('evidence', 0))
            expiry = c.get('valid_until')
            fresh = not expiry or datetime.fromisoformat(expiry).timestamp() >= now
            if c.get('source_usable') and fresh and math.isfinite(score) and score >= threshold and c.get('bias') in votes:
                c['evidence'] = score
                votes[c['bias']].append(c)
        except (ValueError, TypeError):
            continue
    direction = ('BUY' if len(votes['BUY']) > len(votes['SELL']) else
                 'SELL' if len(votes['SELL']) > len(votes['BUY']) else 'WAIT')
    supporters = votes.get(direction, [])
    blocks = []
    levels = {}
    if not supporters:
        blocks.append('No unopposed source-count majority at 75/100; equal opposing votes wait.')
    try:
        bid, ask, atr = (float(context.get(k, 0)) for k in ('bid', 'ask', 'atr'))
        if not context.get('available') or not all(math.isfinite(v) for v in (bid, ask, atr)) or bid <= 0 or ask < bid or atr <= 0:
            raise ValueError()
        if supporters:
            sign = 1 if direction == 'BUY' else -1
            reference = ask if sign == 1 else bid
            distance = max(.5*atr, 2*(ask-bid))
            levels = dict(sl=reference-sign*distance, entry_reference=reference,
                          entry_zone=[bid, ask], source='THREE_SOURCE_STRUCTURE')
            levels.update({f'tp{i}':reference+sign*distance*m for i,m in enumerate((2., 2.5, 3.), 1)})
    except (ValueError, TypeError):
        blocks.append('Fresh ATR/structure and valid executable quote required.')
    if decision.get('news_block'):
        blocks.append('High-impact news protection')
    count = min(maximum, len(supporters))
    families = sorted({'CANDLE_TREND' if c['advisor'] in ('MT5_CANDLES','API_CANDLES')
                       else 'TICK_PRESSURE' for c in supporters})
    return dict(decision, entry_mode='THREE_SOURCE_VOTE', direction=direction,
        dominant_bias=direction, allowed=bool(supporters) and not blocks, blocks=blocks,
        evidence=sum(c['evidence'] for c in supporters)/len(supporters) if supporters else 0.,
        levels=levels, stop_loss=levels.get('sl'), take_profit=levels.get('tp1'),
        entry_reference=levels.get('entry_reference'),
        contributors=contributors, strong_advisor_count=len(supporters),
        strong_advisors=[c['advisor'] for c in supporters], required_strong_advisor_count=1,
        source_position_limit=count, source_vote_threshold=threshold,
        support_analysis_families=families, support_family_count=len(families),
        reasons=['One position per strong agreeing displayed source; ties wait.'],
        data_roles='Displayed three-source votes determine direction and position allowance.')
