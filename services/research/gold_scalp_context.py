"""Bounded higher-timeframe context; SCALP retains direction and order authority."""
import math


def scalp_context(decisions):
    direction = decisions.get('SCALP', {}).get('dominant_bias')
    views = {}
    alignment = 0.
    for name in ('INTRADAY', 'SWING'):
        view = decisions.get(name, {})
        bias = view.get('dominant_bias', 'WAIT')
        score = float(view.get('evidence', 0) or 0)
        usable = (math.isfinite(score) and score >= 15 and bias in ('BUY', 'SELL')
                  and not view.get('news_block')
                  and any(c.get('source_usable') and c.get('bias') == bias
                          for c in view.get('contributors', [])))
        relation = 'NEUTRAL'
        if usable and direction in ('BUY', 'SELL'):
            relation = 'SUPPORT' if bias == direction else 'OPPOSE'
            alignment += (1 if relation == 'SUPPORT' else -1) * min(score, 100) / 200
        views[name] = dict(bias=bias, evidence=score if math.isfinite(score) else 0,
                           usable=usable, relation=relation, execution_enabled=False)
    return dict(role='SCALP_SUPPORT_ONLY', views=views, alignment=round(alignment, 4),
                addition_threshold_adjustment=round(-5 * alignment, 2),
                calibrated_probability=None)
