"""Quote-driven $100 simulated account. This module cannot send MT5 orders."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from uuid import uuid4

from services.utils.atomic_json import atomic_write_json
from config import gold_consensus_settings as settings


class GoldPaperPortfolio:
    def __init__(self, root='data/research/gold_paper', *, learned_policy='off', cross_market_policy='observe'):
        self.run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:8]
        self.root = Path(root)/self.run_id
        self.root.mkdir(parents=True, exist_ok=True)
        self.balance = 100.0
        self.positions = []
        self.trades = []
        self.next_ticket = 1
        self.bid = self.ask = 0.0
        self.now = 0.0
        self.valid_quote = False
        self.valid_exit_quote = False
        self.exit_quote_valid_until = 0.0
        self.quote_valid_until = 0.0
        self.peak_equity = 100.0
        self.max_drawdown = 0.0
        self.learned_policy = learned_policy
        self.cross_market_policy = cross_market_policy

    def mark(self, bid, ask, now, quote_age, *, exit_quote_age=None):
        self.now = now
        exit_quote_age = quote_age if exit_quote_age is None else exit_quote_age
        valid = all(math.isfinite(v) for v in (bid, ask, now)) and bid > 0 and ask >= bid
        self.valid_quote = valid and math.isfinite(quote_age) and 0 <= quote_age <= float(settings.ENTRY_MAX_QUOTE_AGE_SECONDS)
        self.valid_exit_quote = valid and math.isfinite(exit_quote_age) and 0 <= exit_quote_age <= float(settings.EXIT_MAX_FEED_AGE_SECONDS)
        if not self.valid_exit_quote:
            return
        self.bid, self.ask = bid, ask
        self.quote_valid_until = now + float(settings.ENTRY_MAX_QUOTE_AGE_SECONDS) - quote_age
        self.exit_quote_valid_until = now + float(settings.EXIT_MAX_FEED_AGE_SECONDS) - exit_quote_age
        for position in list(self.positions):
            price = bid if position['direction'] == 'BUY' else ask
            sign = 1 if position['direction'] == 'BUY' else -1
            if sign*(price-position['sl']) <= 0:
                self._close(position, 'Simulated emergency stop')
        equity = self.balance+self.floating()
        self.peak_equity = max(self.peak_equity, equity)
        self.max_drawdown = max(self.max_drawdown, self.peak_equity-equity)

    def floating(self, lane=None):
        return sum(self._profit(p) for p in self.positions if lane is None or p['horizon'] == lane)

    def _profit(self, p):
        return (self.bid-p['entry_price'] if p['direction'] == 'BUY' else p['entry_price']-self.ask)-.05

    def details(self, lane):
        return [dict(p, profit=self._profit(p), current_price=self.bid if p['direction'] == 'BUY' else self.ask) for p in self.positions if p['horizon'] == lane]

    def pnl(self, since=0):
        realized = sum(t['profit'] for t in self.trades if t['closed_epoch'] >= since)
        floating = self.floating()
        return dict(available=True, realized=realized, floating=floating, total=realized+floating,
                    balance=self.balance, equity=self.balance+floating, simulated=True,
                    starting_capital=100., max_drawdown_usd=self.max_drawdown, run_id=self.run_id,
                    learned_policy=self.learned_policy, cross_market_policy=self.cross_market_policy)

    def advance_clock(self, now):
        """A quote cannot remain executable while analysis or shutdown takes time."""
        if not math.isfinite(now) or now < self.now:
            self.valid_quote = False
            self.valid_exit_quote = False
            return
        self.now = now
        self.valid_quote = self.valid_quote and now <= self.quote_valid_until
        self.valid_exit_quote = self.valid_exit_quote and now <= self.exit_quote_valid_until

    def open(self, lane, decision, *, margin, stop_mode='CUMULATIVE', minimum_stop_distance=0, now=None):
        if now is not None:
            self.advance_clock(now)
        def blocked(reason):
            return dict(success=False, action='PAPER_OPEN', message=reason)
        if not self.valid_quote or not decision.get('allowed'):
            return blocked('Paper entry requires a fresh quote and permitted decision.')
        cfg = settings.HORIZON_LANES[lane]
        if lane not in ('INTRADAY', 'SWING') and not cfg.get('trade_enabled', True):
            return blocked('Analysis-only horizon cannot open positions.')
        if len(self.positions) >= min(3, int(settings.MAX_POSITION_SLOTS)) or sum(p['horizon'] == lane for p in self.positions) >= (int(cfg['max_positions']) if lane == 'SCALP' else 1):
            return blocked('Paper position capacity reached.')
        if lane == 'SCALP':
            from services.research.gold_scalp_additions import addition_blocks
            blocks = addition_blocks(decision, self.details(lane), self.bid, self.ask)
            if blocks:
                return blocked(' | '.join(blocks))
        if (settings.SESSION_LOSS_STOP_ENABLED
                and self.pnl(self.now-86400)['realized'] <= -float(settings.MAX_SESSION_LOSS_USD)):
            return blocked('Paper rolling 24-hour loss circuit breaker.')
        if self.ask-self.bid > float(settings.MAX_SPREAD_USD):
            return blocked('Paper spread exceeds the configured ceiling.')
        if not isinstance(margin, (int,float)) or not math.isfinite(margin) or margin <= 0:
            return blocked('Broker margin estimate unavailable.')
        free = self.balance+self.floating()-sum(p['margin'] for p in self.positions)
        lane_config = settings.HORIZON_LANES.get(lane, {})
        structural = stop_mode == 'ANALYSIS'
        try:
            configured_cap = getattr(settings, 'MAX_TRADE_RISK_USD', None)
            fallback_budget = lane_config.get('individual_stop_loss_usd') or configured_cap
            stop_budget = abs(float(decision['stop_loss'])-self.ask if decision.get('direction') == 'BUY'
                              else float(decision['stop_loss'])-self.bid) if structural else float(fallback_budget)
        except (KeyError, TypeError, ValueError):
            return blocked('Paper protective stop unavailable.')
        cap_enabled = configured_cap is not None and math.isfinite(float(configured_cap)) and float(configured_cap) > 0
        if not math.isfinite(stop_budget) or stop_budget <= 0 or (not structural and cap_enabled and stop_budget > float(configured_cap)):
            return blocked('Paper stop budget is invalid.')
        if free < margin+stop_budget+.10:
            return blocked('Insufficient simulated free margin for $100 profile.')
        direction = decision.get('direction')
        if direction not in ('BUY', 'SELL'):
            return blocked('Invalid paper direction.')
        sign = 1 if direction == 'BUY' else -1
        price = self.ask if sign == 1 else self.bid
        try:
            target, analysis_stop = float(decision['take_profit']), float(decision['stop_loss'])
        except (KeyError, TypeError, ValueError):
            return blocked('Paper analysis levels unavailable.')
        reward, risk = sign*(target-price), sign*(price-analysis_stop)
        if not all(math.isfinite(v) for v in (reward, risk)) or min(reward, risk) <= 0:
            return blocked('Paper analysis levels invalid for current quote.')
        if (reward/risk < float(settings.MIN_ANALYSIS_REWARD_RISK)
                or (self.ask-self.bid)/reward > float(settings.MAX_SPREAD_TO_ANALYSIS_TARGET_RATIO)):
            return blocked('Paper analysis reward/risk or spread ratio failed.')
        zone = decision.get('levels', {}).get('entry_zone', [])
        if isinstance(zone, (list, tuple)) and len(zone) == 2:
            low, high = sorted(map(float, zone))
            tolerance = (self.ask-self.bid)*float(settings.ENTRY_ZONE_TOLERANCE_SPREADS)
            if not (math.isfinite(low) and math.isfinite(high) and low-tolerance <= price <= high+tolerance):
                return blocked('Paper quote outside entry zone.')
        entry = price+sign*.05
        try:
            sl = entry-sign*stop_budget if stop_mode == 'INDIVIDUAL' else float(decision['stop_loss'])
        except (TypeError, ValueError, KeyError):
            return blocked('Paper protective stop unavailable.')
        risk = sign*(entry-sl)
        if not math.isfinite(risk) or risk <= 0 or (not structural and cap_enabled and risk > float(configured_cap)+.000001):
            return blocked('Paper planned stop exposure exceeds the configured trade-risk cap.')
        reference = self.bid if sign == 1 else self.ask
        if sign*(reference-sl) < minimum_stop_distance:
            return blocked('Paper stop violates broker minimum distance.')
        position = dict(ticket=self.next_ticket, horizon=lane, direction=direction,
                        volume=.01, entry_price=entry, sl=sl, margin=margin,
                        learned_policy=decision.get('learned_policy', {}),
                        cross_market=decision.get('cross_market', {}),
                        opened_epoch=self.now, time=datetime.fromtimestamp(self.now, timezone.utc).isoformat())
        self.next_ticket += 1
        self.positions.append(position)
        self.save()
        return dict(success=True, action='PAPER_OPEN', message=f'Simulated {direction} 0.01 lot', ticket=position['ticket'])

    def _close(self, position, reason):
        profit = self._profit(position)
        trade = dict(position, profit=profit, reason=reason, closed_epoch=self.now,
                     closed_at=datetime.fromtimestamp(self.now, timezone.utc).isoformat(),
                     exit_price=self.bid-.05 if position['direction'] == 'BUY' else self.ask+.05,
                     simulated=True)
        self.balance += profit
        self.positions.remove(position)
        self.trades.append(trade)
        with (self.root/'trades.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(trade)+'\n')

    def close_lane(self, lane, reason, *, now=None, tickets=None):
        if now is not None:
            self.advance_clock(now)
        if not self.valid_exit_quote:
            return dict(closed_count=0, failures=['No fresh executable quote'])
        selected = [p for p in self.positions if p['horizon'] == lane
                    and (tickets is None or p['ticket'] in tickets)]
        for p in selected:
            self._close(p, reason)
        self.save()
        return dict(closed_count=len(selected), failures=[])

    def save(self):
        equity = self.balance+self.floating()
        self.peak_equity = max(self.peak_equity, equity)
        self.max_drawdown = max(self.max_drawdown, self.peak_equity-equity)
        atomic_write_json(self.root/'account.json', dict(**self.pnl(), positions=self.positions,
                          trades=len(self.trades), quote_valid=self.valid_quote,
                          note='Sampled-quote simulation; gaps, unobserved ticks, commissions and swap are not fully modeled'), indent=2)
