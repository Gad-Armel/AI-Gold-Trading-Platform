"""Broker-derived inverse positions and matched-pair P/L; read-only reporting."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from config import gold_inverse_settings as cfg
from services.market_data.gold_broker_clock import to_broker_time, broker_epoch_to_utc
from services.dashboard.gold_dual_reset import load_display_reset
from services.research.gold_s30_execution import account_fingerprint


def summarize_groups(deals, positions, entry_magic, selected_ids=None, reset_epoch=None):
    grouped = defaultdict(list)
    for deal in deals:
        if deal.symbol == cfg.SYMBOL and deal.type in (0, 1):
            grouped[int(deal.position_id)].append(deal)
    held = {int(getattr(position, 'identifier', 0) or position.ticket): position for position in positions}
    realized, floating, closed, selected = 0., 0., [], set()
    for identifier, group in grouped.items():
        incoming = [deal for deal in group if deal.entry == 0 and deal.magic == entry_magic]
        if not incoming or (selected_ids is not None and identifier not in selected_ids):
            continue
        selected.add(identifier)
        outgoing = [deal for deal in group if deal.entry in (1, 3)]
        net = sum(deal.profit+deal.commission+deal.swap+deal.fee for deal in group)
        position = held.get(identifier)
        if position is not None:
            floating += float(position.profit)+float(getattr(position, 'swap', 0.))+net
        elif outgoing and abs(sum(deal.volume for deal in incoming)-sum(deal.volume for deal in outgoing)) < 1e-8:
            last = max(outgoing, key=lambda deal: deal.time_msc)
            if reset_epoch is not None and broker_epoch_to_utc(last.time_msc/1000).timestamp() < reset_epoch:
                continue
            realized += net
            first = min(incoming, key=lambda deal: deal.time_msc)
            closed.append(dict(position_id=identifier, direction='BUY' if first.type == 0 else 'SELL',
                volume=sum(deal.volume for deal in incoming), profit=net,
                closed_at=broker_epoch_to_utc(last.time_msc/1000).isoformat()))
    closed.sort(key=lambda row: row['closed_at'], reverse=True)
    return dict(realized=realized, floating=floating, total=realized+floating,
                closed_trades=closed[:30], identifiers=selected)


def trading_snapshot(mt5, *, now=None):
    now = now or datetime.now(timezone.utc)
    positions = mt5.positions_get(symbol=cfg.SYMBOL)
    deals = mt5.history_deals_get(to_broker_time(now-timedelta(days=7)), to_broker_time(now))
    if positions is None or deals is None:
        raise RuntimeError('Broker positions/history unavailable; P/L cannot be inferred')
    unique = {deal.ticket: deal for deal in deals}
    deals = list(unique.values())
    source_ids = set()
    linked_inverse_ids = set()
    for deal in deals:
        comment = getattr(deal, 'comment', '')
        if deal.magic == cfg.MAGIC and deal.entry == 0 and comment.startswith('INV:') and comment[4:].isdigit():
            source_ids.add(int(comment[4:]))
            linked_inverse_ids.add(int(deal.position_id))
    inverse = summarize_groups(deals, positions, cfg.MAGIC)
    paired_main = summarize_groups(deals, positions, cfg.SOURCE_MAGIC, source_ids)
    reset = load_display_reset(account_fingerprint(mt5.account_info())) if hasattr(mt5, 'account_info') else None
    cutoff = reset['reset_epoch'] if reset else None
    inverse_display = summarize_groups(deals, positions, cfg.MAGIC, reset_epoch=cutoff)
    main_display = summarize_groups(deals, positions, cfg.SOURCE_MAGIC, reset_epoch=cutoff)
    paired_display = summarize_groups(deals, positions, cfg.SOURCE_MAGIC, source_ids, reset_epoch=cutoff)
    paired_display['floating'] -= reset.get('paired_main_open_baseline', 0.) if reset else 0.
    paired_display['total'] = paired_display['realized']+paired_display['floating']
    for summary, key in ((inverse_display, 'inverse_open_baseline'), (main_display, 'main_open_baseline')):
        summary['actual_floating'] = summary['floating']
        summary['floating'] -= reset.get(key, 0.) if reset else 0.
        summary['total'] = summary['realized']+summary['floating']
    rows = []
    for position in positions:
        if position.magic != cfg.MAGIC:
            continue
        comment = getattr(position, 'comment', '')
        rows.append(dict(ticket=position.ticket, horizon='INVERSE',
            source_position_id=comment[4:] if comment.startswith('INV:') else None,
            direction='BUY' if position.type == 0 else 'SELL', volume=position.volume,
            entry_price=position.price_open, current_price=position.price_current,
            sl=position.sl, tp=position.tp, profit=position.profit))
    open_ids = {int(getattr(position, 'identifier', 0) or position.ticket)
                for position in positions if position.magic == cfg.MAGIC}
    complete_history = open_ids <= inverse['identifiers']
    matched_complete = (complete_history and source_ids <= paired_main['identifiers']
                        and inverse['identifiers'] <= linked_inverse_ids)
    return dict(available=True, updated_at=now.isoformat(), positions=rows,
        closed_trades=inverse_display['closed_trades'], reset_epoch=cutoff,
        main_display=dict(closed_trades=main_display['closed_trades'],
            pnl=dict(available=True, **{key: main_display[key] for key in ('realized', 'floating', 'total', 'actual_floating')})),
        pnl=dict(available=complete_history, **{key: inverse_display[key] if complete_history else None
                                             for key in ('realized', 'floating', 'total', 'actual_floating')}),
        scope='Display change since reset (open P/L baseline included)' if reset else 'Broker history: last 7 days',
        paired=dict(available=matched_complete, linked_sources=len(source_ids),
            main_net=paired_display['total'], inverse_net=inverse_display['total'],
            main_actual_floating=paired_main['floating'],
            combined_net=paired_display['total']+inverse_display['total'] if matched_complete else None,
            scope='Linked experiment since display reset' if reset else 'Linked main/inverse experiment only; excludes unmirrored main trades'),
        note='Position cards show broker floating P/L; aggregate open P/L includes recorded fees/swap.')
