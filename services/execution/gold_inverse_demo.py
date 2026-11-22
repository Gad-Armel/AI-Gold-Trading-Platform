"""Separate same-account inverse demo execution with durable one-shot intents."""
import math

from config import gold_consensus_settings as main
from config import gold_inverse_settings as cfg
from config import settings as core
from services.bot.emergency_stop import is_emergency_stop_enabled
from services.execution.gold_consensus_demo_broker import _as_dict, _filling_mode
from services.market_data.gold_broker_clock import quote_age
from services.research.gold_s30_execution import account_fingerprint
from services.execution.gold_pair_exit import exit_requested


class InverseDemoExecutor:
    def __init__(self, mt5, state, persist):
        self.mt5, self.state, self.persist = mt5, state, persist
        self.events = []
        self.identity = state['account_fingerprint']
        state.setdefault('links', {})

    def guard(self):
        account = self.mt5.account_info()
        terminal = self.mt5.terminal_info()
        if (account is None or account.trade_mode != self.mt5.ACCOUNT_TRADE_MODE_DEMO
                or account_fingerprint(account) != self.identity or account.currency != 'USD'
                or account.margin_mode != self.mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING):
            raise RuntimeError('Locked USD DEMO hedging account required; account changes are blocked')
        if not getattr(account, 'hedge_allowed', True):
            raise RuntimeError('Opposite positions are not permitted by this account')
        if (terminal is None or not terminal.connected or not terminal.trade_allowed
                or getattr(terminal, 'tradeapi_disabled', False) or not account.trade_allowed
                or not account.trade_expert or core.ENABLE_LIVE_TRADING):
            raise RuntimeError('Demo automated trading is unavailable')

    def positions(self):
        rows = self.mt5.positions_get(symbol=cfg.SYMBOL)
        if rows is None:
            raise RuntimeError('Position snapshot unavailable; absence cannot be inferred')
        return list(rows)

    def source_id(self, position):
        return str(getattr(position, 'identifier', 0) or position.ticket)

    def tick(self):
        tick = self.mt5.symbol_info_tick(cfg.SYMBOL)
        if tick is None or not all(math.isfinite(float(value)) and value > 0 for value in (tick.bid, tick.ask)) or tick.ask < tick.bid:
            raise RuntimeError('Valid executable quote required')
        if quote_age(tick.time_msc/1000) > main.MAX_QUOTE_AGE_SECONDS:
            raise RuntimeError('Quote is stale or future-dated')
        return tick

    def send(self, request, link, phase):
        self.guard()
        checked = self.mt5.order_check(request)
        if checked is None or getattr(checked, 'retcode', -1) not in (0, self.mt5.TRADE_RETCODE_DONE):
            link[phase] = 'CHECK_FAILED'
            self.persist(self.state)
            return
        link[phase] = 'INTENT'
        self.persist(self.state)
        try:
            result = _as_dict(self.mt5.order_send(request))
        except Exception as error:
            result = dict(error=str(error))
        code = result.get('retcode')
        link[phase] = ('REPORTED_DONE' if code == 10009 else 'UNCERTAIN'
                       if code in (None, 10008, 10010, 10012, 10031) else 'REJECTED')
        self.events.append(dict(action=phase, request=request, result=result))
        self.persist(self.state)

    def close(self, position, link):
        if link.get('close') in ('INTENT', 'UNCERTAIN', 'REPORTED_DONE'):
            return
        tick = self.tick()
        info = self.mt5.symbol_info(cfg.SYMBOL)
        filling = _filling_mode(self.mt5, info) if info else None
        if filling is None:
            raise RuntimeError('No supported filling mode')
        request = dict(action=self.mt5.TRADE_ACTION_DEAL, symbol=cfg.SYMBOL,
            position=position.ticket, volume=position.volume,
            type=self.mt5.ORDER_TYPE_SELL if position.type == self.mt5.POSITION_TYPE_BUY else self.mt5.ORDER_TYPE_BUY,
            price=tick.bid if position.type == self.mt5.POSITION_TYPE_BUY else tick.ask,
            deviation=main.ORDER_DEVIATION_POINTS, magic=cfg.MAGIC, comment='InverseSourceClosed',
            type_time=self.mt5.ORDER_TIME_GTC, type_filling=filling)
        self.send(request, link, 'close')

    def open(self, source, link, now):
        self.guard()
        positions = self.positions()
        pending = self.mt5.orders_get(symbol=cfg.SYMBOL)
        if pending is None or pending:
            raise RuntimeError('Pending order snapshot unavailable or orders not reconciled')
        controlled = {cfg.MAGIC, main.MAGIC_NUMBER} | {lane['magic'] for lane in main.HORIZON_LANES.values()}
        if any(position.magic not in controlled for position in positions):
            raise RuntimeError('External XAUUSD positions present')
        if (len(positions) >= cfg.MAX_COMBINED_POSITIONS or
                sum(position.magic == cfg.MAGIC for position in positions) >= cfg.MAX_INVERSE_POSITIONS):
            link['open'] = 'CAPACITY_SKIPPED'
            self.persist(self.state)
            return
        sources = [position for position in positions if position.magic == cfg.SOURCE_MAGIC
                   and self.source_id(position) == self.source_id(source)]
        if not sources:
            link['open'] = 'SOURCE_ALREADY_CLOSED'
            self.persist(self.state)
            return
        source = sources[0]
        opened = float(getattr(source, 'time_msc', 0) or source.time*1000)/1000-main.MT5_SERVER_UTC_OFFSET_SECONDS
        if not 0 <= now-opened <= cfg.MAX_ENTRY_DELAY_SECONDS:
            link['open'] = 'SOURCE_TOO_OLD'
            self.persist(self.state)
            return
        if (source.type not in (self.mt5.POSITION_TYPE_BUY, self.mt5.POSITION_TYPE_SELL)
                or not math.isclose(source.volume, cfg.LOT, abs_tol=1e-10)
                or not math.isfinite(source.sl) or source.sl <= 0):
            raise RuntimeError('Protected 0.01-lot source required')
        info, tick = self.mt5.symbol_info(cfg.SYMBOL), self.tick()
        if info is None or not getattr(info, 'visible', False):
            raise RuntimeError('XAUUSD metadata unavailable')
        if (not info.volume_min <= cfg.LOT <= info.volume_max or info.volume_step <= 0
                or abs(cfg.LOT/info.volume_step-round(cfg.LOT/info.volume_step)) > 1e-7):
            raise RuntimeError('Exact 0.01 volume unsupported')
        if tick.ask-tick.bid > main.MAX_SPREAD_USD:
            raise RuntimeError('Inverse spread ceiling exceeded')
        buy = source.type == self.mt5.POSITION_TYPE_SELL
        price = tick.ask if buy else tick.bid
        distance = abs(source.price_open-source.sl)
        step = float(getattr(info, 'trade_tick_size', info.point) or info.point)
        if not math.isfinite(distance) or min(distance, step) <= 0:
            raise RuntimeError('Invalid protective distance')
        raw_stop = price-distance if buy else price+distance
        stop = round((math.floor(raw_stop/step) if buy else math.ceil(raw_stop/step))*step,
                     int(getattr(info, 'digits', 10)))
        minimum = float(getattr(info, 'trade_stops_level', 0))*info.point
        if stop <= 0 or (tick.bid-stop if buy else stop-tick.ask) < max(step, minimum):
            raise RuntimeError('Inverse SL violates broker distance; never open naked')
        order_type = self.mt5.ORDER_TYPE_BUY if buy else self.mt5.ORDER_TYPE_SELL
        risk = self.mt5.order_calc_profit(order_type, cfg.SYMBOL, cfg.LOT, price, stop)
        if risk is None or not math.isfinite(risk) or not -cfg.MAX_PLANNED_RISK_USD <= risk < 0:
            raise RuntimeError('Inverse planned stop risk exceeds budget or cannot be valued')
        filling = _filling_mode(self.mt5, info)
        if filling is None:
            raise RuntimeError('No supported filling mode')
        request = dict(action=self.mt5.TRADE_ACTION_DEAL, symbol=cfg.SYMBOL, volume=cfg.LOT,
            type=order_type, price=price, sl=stop, tp=0., deviation=main.ORDER_DEVIATION_POINTS,
            magic=cfg.MAGIC, comment='INV:'+self.source_id(source),
            type_time=self.mt5.ORDER_TIME_GTC, type_filling=filling)
        self.send(request, link, 'open')

    def cycle(self, now, *, allow_new=True, stop=False):
        self.events = []
        self.guard()
        positions = self.positions()
        sources = {self.source_id(position): position for position in positions if position.magic == cfg.SOURCE_MAGIC}
        owned = [position for position in positions if position.magic == cfg.MAGIC]
        owned_tickets = {position.ticket for position in owned}
        for link in self.state['links'].values():
            if link.get('inverse_ticket') and link['inverse_ticket'] not in owned_tickets:
                link['close'] = 'POSITION_ABSENT'
        for position in owned:
            comment = getattr(position, 'comment', '')
            if not comment.startswith('INV:') or not comment[4:].isdigit():
                raise RuntimeError('Unrecognized inverse position comment; manual review required')
            source_id = comment[4:]
            link = self.state['links'].setdefault(source_id, dict(open='RECOVERED'))
            link['open'] = 'POSITION_CONFIRMED'
            link['inverse_ticket'] = position.ticket
            if stop or source_id not in sources or exit_requested(source_id, self.identity):
                self.close(position, link)
        if not self.state.get('bootstrapped'):
            for source_id in sources:
                self.state['links'].setdefault(source_id, dict(open='STARTUP_BASELINE_SKIPPED'))
            self.state['bootstrapped'] = True
            self.persist(self.state)
        if allow_new and not stop and not is_emergency_stop_enabled():
            for source_id, source in sources.items():
                if exit_requested(source_id, self.identity):
                    continue
                if source_id in self.state['links']:
                    continue
                link = self.state['links'].setdefault(source_id, dict(
                    open='DISCOVERED', source_ticket=source.ticket,
                    source_direction='BUY' if source.type == self.mt5.POSITION_TYPE_BUY else 'SELL',
                    inverse_direction='SELL' if source.type == self.mt5.POSITION_TYPE_BUY else 'BUY',
                    signal_policy='INHERIT_MAIN_ANALYSIS_REVERSE_CONFIRMED_FILL'))
                self.persist(self.state)
                try:
                    self.open(source, link, now)
                except Exception as error:
                    link.update(open='SKIPPED', error=str(error))
                    self.persist(self.state)
        pending = self.mt5.orders_get(symbol=cfg.SYMBOL)
        pending_count = None if pending is None else sum(order.magic == cfg.MAGIC for order in pending)
        self.persist(self.state)
        return dict(source_positions=len(sources), inverse_positions=len(owned), pending_inverse_orders=pending_count,
                    inverse_floating_profit=sum(position.profit for position in owned), events=self.events,
                    uncertain_links=[source_id for source_id, link in self.state['links'].items()
                                     if link.get('open') in ('INTENT', 'UNCERTAIN') or
                                     link.get('close') in ('INTENT', 'UNCERTAIN')])
