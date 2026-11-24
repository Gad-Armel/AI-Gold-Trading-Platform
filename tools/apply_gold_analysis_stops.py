"""Replace fixed stops on owned demo SCALP positions with fresh analysis stops."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import gold_consensus_settings as settings
from services.execution.demo_session_guard import arm_demo_session,validate_demo_session_identity
from config import scalping_settings
from services.execution.gold_consensus_demo_broker import _stop_grid_block,_planned_risk_block
from services.market_data.gold_broker_clock import quote_age


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true')
    apply=parser.parse_args().apply
    import MetaTrader5 as mt5
    if not mt5.initialize():raise RuntimeError(mt5.last_error())
    try:
        account=mt5.account_info()
        arm_demo_session(scalping_settings.SCALPING_REQUIRED_DEMO_CONFIRMATION,account,mt5)
        valid,reason=validate_demo_session_identity(account,mt5)
        if not valid or account.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO:raise RuntimeError(reason)
        if settings.HORIZON_LANES['SCALP']['stop_mode']!='ANALYSIS':raise RuntimeError('Analysis-stop policy required')
        status=json.loads((ROOT/'data/runtime/gold_consensus_status.json').read_text())
        if time.time()-datetime.fromisoformat(status['updated_at']).timestamp()>10:raise RuntimeError('Stale main analysis')
        decision=status['lanes']['SCALP']['decision'];sl=float(decision['levels']['sl'])
        positions=mt5.positions_get(symbol=settings.SYMBOL)
        if positions is None:raise RuntimeError('Positions unavailable')
        info=mt5.symbol_info(settings.SYMBOL);tick=mt5.symbol_info_tick(settings.SYMBOL)
        if not tick or not -5<=quote_age(tick.time_msc/1000)<=settings.MAX_QUOTE_AGE_SECONDS:raise RuntimeError('Stale quote')
        report=[]
        for position in positions:
            if position.magic!=631011:continue
            direction='BUY' if position.type==mt5.ORDER_TYPE_BUY else 'SELL'
            if decision['direction']!=direction:raise RuntimeError('Current analysis does not support held position')
            block=_stop_grid_block(info,direction,tick.bid,tick.ask,sl)
            if block:raise RuntimeError(block['message'])
            block=_planned_risk_block(mt5,direction,position.volume,position.price_open,sl,enforce_budget=False)
            if block:raise RuntimeError(block['message'])
            item=dict(ticket=position.ticket,old_sl=position.sl,new_sl=sl,
                planned_stop_profit=mt5.order_calc_profit(position.type,settings.SYMBOL,position.volume,position.price_open,sl))
            if apply:
                result=mt5.order_send(dict(action=mt5.TRADE_ACTION_SLTP,symbol=settings.SYMBOL,
                    position=position.ticket,sl=sl,tp=position.tp,magic=position.magic))
                if not result or result.retcode!=mt5.TRADE_RETCODE_DONE:raise RuntimeError(str(result))
                actual=mt5.positions_get(ticket=position.ticket)
                if actual and abs(actual[0].sl-sl)>info.point/2:raise RuntimeError('Stop update not confirmed')
                item['confirmed']=bool(actual)
            report.append(item)
        output=dict(at=datetime.now(timezone.utc).isoformat(),applied=apply,positions=report)
        folder=ROOT/'data/research/scalp_loss_diagnosis_20261009';folder.mkdir(exist_ok=True)
        (folder/'analysis_stop_change.json').write_text(json.dumps(output,indent=2))
        print(json.dumps(output,indent=2))
    finally:mt5.shutdown()


if __name__=='__main__':main()
