"""Read-only MT5 deal audit and completed-bar export. Never sends orders."""
from __future__ import annotations
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config import gold_consensus_settings as settings


def main():
    import MetaTrader5 as mt5
    import pandas as pd
    target = Path('data/research/xauusd_audit')
    target.mkdir(parents=True, exist_ok=True)
    if not mt5.initialize():
        raise RuntimeError(f'MT5 unavailable: {mt5.last_error()}')
    try:
        end = datetime.now(timezone.utc)
        # The connected broker stamps its MT5 history at UTC+3 (measured).
        offset = settings.MT5_SERVER_UTC_OFFSET_SECONDS
        deals = mt5.history_deals_get(end - timedelta(days=30) + timedelta(seconds=offset), end + timedelta(seconds=offset))
        if deals is None:
            raise RuntimeError(f'History unavailable: {mt5.last_error()}')
        magics = {631011: 'SCALP', 631012: 'INTRADAY', 631013: 'SWING'}
        owners = {d.position_id: magics[d.magic] for d in deals if d.magic in magics and d.entry == 0}
        grouped = {}
        for deal in deals:
            if deal.position_id in owners:
                grouped.setdefault(deal.position_id, []).append(deal)
        trades = []
        for pid, rows in grouped.items():
            ins = [d for d in rows if d.entry == 0]
            outs = [d for d in rows if d.entry in (1, 3)]
            if not outs or sum(d.volume for d in outs) + 1e-9 < sum(d.volume for d in ins):
                continue
            trades.append(dict(position_id=pid, horizon=owners[pid],
                opened_at=min(d.time for d in ins)-offset, closed_at=max(d.time for d in outs)-offset,
                hold_seconds=max(d.time for d in outs)-min(d.time for d in ins),
                net_profit=sum(sum(getattr(d, k, 0) for k in ('profit','commission','swap','fee')) for d in rows),
                close_comment=outs[-1].comment))
        pd.DataFrame(trades).to_csv(target / 'closed_trades.csv', index=False)
        summary = {'as_of': end.isoformat(), 'lookback_days': 30, 'broker_utc_offset_seconds':offset, 'lanes': {}}
        for name in magics.values():
            selected = sorted([t for t in trades if t['horizon'] == name], key=lambda t:t['closed_at'])
            pnls = [t['net_profit'] for t in selected]
            wins, losses = sum(max(p,0) for p in pnls), -sum(min(p,0) for p in pnls)
            equity = peak = drawdown = 0
            for p in pnls:
                equity += p; peak = max(peak,equity); drawdown=max(drawdown,peak-equity)
            summary['lanes'][name] = dict(trades=len(pnls), net_profit=round(sum(pnls),2),
                win_rate=sum(p>0 for p in pnls)/len(pnls) if pnls else None,
                profit_factor=wins/losses if losses else None, closed_trade_drawdown=round(drawdown,2),
                average_hold_seconds=sum(t['hold_seconds'] for t in selected)/len(selected) if selected else None)
        summary['bars'] = {}
        for name in ('M5','M15','H1'):
            if (target/(name+'.csv')).exists():
                summary['bars'][name] = 'Existing research export preserved'
                continue
            bars = mt5.copy_rates_from_pos('XAUUSD', getattr(mt5,'TIMEFRAME_'+name),1,50000)
            if bars is not None:
                pd.DataFrame(bars).to_csv(target / (name+'.csv'),index=False)
                summary['bars'][name] = len(bars)
            else:
                summary['bars'][name] = str(mt5.last_error())
        (target/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        print(json.dumps(summary,indent=2))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
