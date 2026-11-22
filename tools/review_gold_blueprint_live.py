"""Read-only broker evidence for the four-blueprint review; no trading calls."""
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import statistics

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import gold_consensus_settings as settings
from services.market_data.gold_broker_clock import to_broker_time, broker_epoch_to_utc
from services.execution.gold_consensus_demo_broker import recent_closed_consensus_trades
from services.research.gold_trade_episode_audit import episode_audit


def summary(trades):
    values = [t['profit'] for t in trades]
    wins = [p for p in values if p > 0]
    losses = [p for p in values if p < 0]
    average_win = statistics.mean(wins) if wins else None
    average_loss = -statistics.mean(losses) if losses else None
    return dict(closed_trades=len(values), net=round(sum(values),2),
        mean=statistics.mean(values) if values else None,
        win_rate=len(wins)/len(values) if values else None,
        profit_factor=sum(wins)/(-sum(losses)) if losses else None,
        average_win=average_win, average_loss=average_loss,
        breakeven_win_rate=average_loss/(average_win+average_loss) if wins and losses else None)


def main():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(mt5.last_error())
    try:
        account = mt5.account_info()
        assert account and account.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
        now = datetime.now(timezone.utc)
        start = datetime(2026,10,9,tzinfo=timezone.utc)
        deals = mt5.history_deals_get(to_broker_time(start), to_broker_time(now))
        if deals is None:
            raise RuntimeError('Broker history unavailable')
        trades = recent_closed_consensus_trades(mt5, limit=10000, magic_number=631011,
                                               strict=True, deals_snapshot=deals)
        cohorts = {}
        for label, cutoff in [('scalp_only','2026-10-09T01:33:26+00:00'),
                               ('reactive_entries','2026-10-09T02:23:49+00:00'),
                               ('profit_lock','2026-10-09T05:13:55+00:00')]:
            selected = [t for t in trades if t['opened_at'] >= cutoff]
            cohorts[label] = dict(cutoff=cutoff, **summary(selected), trades=selected,
                                  episode_audit=episode_audit(selected))
        info = mt5.symbol_info(settings.SYMBOL)
        tick = mt5.symbol_info_tick(settings.SYMBOL)
        owned = [p for p in mt5.positions_get(symbol=settings.SYMBOL) or () if p.magic == 631011]
        owned_ids = {d.position_id for d in deals if d.magic == 631011}
        charges = {key:sum(getattr(d,key,0) for d in deals if d.position_id in owned_ids)
                   for key in ('commission','swap','fee')}
        opens = []
        for p in owned:
            stop_value = mt5.order_calc_profit(p.type,settings.SYMBOL,p.volume,p.price_open,p.sl) if p.sl > 0 else None
            opens.append(dict(ticket=p.ticket, volume=p.volume, profit=p.profit,
                              protected=p.sl > 0, stop_exposure_from_actual_fill=stop_value))
        report = dict(as_of=now.isoformat(), mode='DEMO', cohorts=cohorts,
                      observed_position_deal_charges=charges, open_positions=opens,
                      broker_symbol={name:getattr(info,name) for name in
                          ('digits','point','trade_tick_size','trade_contract_size','volume_min','volume_step',
                           'trade_stops_level','trade_freeze_level','trade_exemode','filling_mode')},
                      current_spread=round(tick.ask-tick.bid,6),
                      limitations=['Overlapping cohorts are descriptive, not causal A/B comparisons.',
                                   'Few short-window outcomes do not establish long-run profitability.',
                                   'Net position history includes observed commission, swap and fee.',
                                   'Later balance-level commissions may not be attributable to these positions.',
                                   'History starts at UTC midnight; positions opened earlier are excluded if their entry is missing.'])
        target = ROOT/'data/research/blueprint_review_20261009/live_broker_audit.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2))
        print(json.dumps({k:v for k,v in report.items() if k != 'cohorts'},indent=2))
        print(json.dumps({k:{n:v for n,v in c.items() if n not in ('trades','episode_audit')} for k,c in cohorts.items()},indent=2))
        print(json.dumps({k:{n:v for n,v in c['episode_audit'].items() if n != 'clusters'}
                          for k,c in cohorts.items()},indent=2))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
