"""Bounded counterfactual labels for both locally blocked and attempted setups."""
import math


def observe_labels(state, decision, *, now, bid, ask, feed_age, attempted=False):
    base = dict(execution_enabled=False, label_policy='PAPER_FIXED_BARRIERS_V1',
                latency_seconds=.35, round_trip_cost_price=.3, horizon_seconds=60,
                limitations=['Loop-sampled quotes can miss intraloop barrier crossings.',
                    'Counterfactual fixed-barrier labels differ from adaptive broker exits.',
                    'No model is trained or promoted; overlapping labels are correlated.'])
    pending = state.setdefault('pending', {})
    seen = state.setdefault('seen', {})
    groups = state.setdefault('groups', {})
    valid_quote = (all(isinstance(value, (int, float)) and math.isfinite(value)
                       for value in (now, bid, ask, feed_age)) and
                   0 <= feed_age <= 1 and bid > 0 and ask >= bid)
    if valid_quote:
        quote_epoch = now-feed_age
        for setup_id, track in list(pending.items()):
            sign = track['sign']
            if 'entry' not in track:
                if quote_epoch < track['created']+.35:
                    continue
                if quote_epoch >= track['expires']:
                    state['censored'] = state.get('censored', 0)+1
                    del pending[setup_id]
                    continue
                entry = ask if sign > 0 else bid
                risk = sign*(entry-track['stop'])
                if risk <= 0:
                    state['censored'] = state.get('censored', 0)+1
                    del pending[setup_id]
                    continue
                track.update(entry=entry, risk=risk, filled_epoch=quote_epoch)
            if quote_epoch < track['filled_epoch']:
                continue
            move = sign*((bid if sign > 0 else ask)-track['entry'])
            if move <= -track['risk'] or move >= 1.5*track['risk'] or quote_epoch >= track['expires']:
                group = groups.setdefault(track['group'], dict(labels=0, wins=0, net_r_sum=0.))
                net_r = (move-.3)/track['risk']
                group['labels'] += 1
                group['wins'] += int(net_r > 0)
                group['net_r_sum'] += net_r
                del pending[setup_id]
        observation = decision.get('s30_entry', {})
        candidate = observation.get('fast_candidate', {})
        setup_id = candidate.get('setup_id')
        direction = decision.get('direction')
        stop = decision.get('stop_loss')
        if (observation.get('available') and setup_id and direction in ('BUY', 'SELL') and
                candidate.get('direction') == direction and isinstance(stop, (int, float)) and
                math.isfinite(stop) and stop > 0):
            if setup_id not in seen:
                seen[setup_id] = now
                if len(pending) < 200:
                    pending[setup_id] = dict(created=now, expires=now+60, stop=stop,
                        sign=1 if direction == 'BUY' else -1, group='NOT_ATTEMPTED')
                else:
                    state['censored'] = state.get('censored', 0)+1
            if attempted and setup_id in pending:
                pending[setup_id]['group'] = 'ATTEMPTED'
        for setup_id, created in list(seen.items()):
            if now-created > 3600:
                del seen[setup_id]
    return dict(base, pending=len(pending), censored=state.get('censored', 0),
                groups={key: dict(value, mean_net_r=value['net_r_sum']/value['labels'])
                        for key, value in groups.items() if value['labels']})
