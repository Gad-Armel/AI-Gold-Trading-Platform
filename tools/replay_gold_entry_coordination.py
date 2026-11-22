"""Causal recorded-signal challenger, deliberately not a full main-bot replay."""
import bisect
import argparse
import json
import hashlib
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import gold_consensus_settings as settings
from services.execution.gold_paper_portfolio import GoldPaperPortfolio
from services.research.gold_adaptive_exit import evaluate_adaptive_exit
from services.research.gold_entry_coordination import assess_entry_coordination
from services.research.gold_entry_momentum import entry_momentum_blocks, scalp_confirmation_blocks
from services.research.gold_candle_confirmation import confirm_next_move
from services.research.gold_flow_exit import evaluate_flow_exit
from services.research.gold_micro_flow import MicroFlow
from services.research.gold_fast_protection import quote_protection
from services.research.gold_position_conscience import assess_position_conscience
from services.research.gold_scalp_guard import reconcile, reentry_blocks


def epoch(value):
    return datetime.fromisoformat(value).timestamp()


def freeze_capture(folder, *, start_utc=None):
    """Read one immutable set of complete journal lines for both variants."""
    lines=(folder/'observations.jsonl').read_text(encoding='utf-8').splitlines(keepends=True)
    if lines and not lines[-1].endswith('\n'):
        lines.pop()  # A concurrent append may leave a partial trailing record.
    parsed=[(line,json.loads(line)) for line in lines]
    excluded=0
    if start_utc is not None:
        if datetime.fromisoformat(start_utc).tzinfo is None:
            raise ValueError('Prospective start must include a UTC offset')
        cutoff=epoch(start_utc)
        selected=[]
        for line,row in parsed:
            updated=row.get('status',{}).get('updated_at')
            if (updated and epoch(row['observed_at'])>=cutoff and epoch(updated)>=cutoff):
                selected.append((line,row))
            else:
                excluded+=1
        parsed=selected
    frozen=tuple(line for line,_ in parsed)
    observations=[row for _,row in parsed]
    observations=sorted((r for r in observations if 'candles' in r and 'status' in r),
                        key=lambda r:epoch(r['observed_at']))
    if not observations:
        raise ValueError('No complete captured observations')
    return frozen,dict(first=observations[0]['observed_at'],last=observations[-1]['observed_at'],
        complete_observations=len(observations),sha256=hashlib.sha256(''.join(frozen).encode()).hexdigest(),
        start_utc=start_utc,excluded_before_cutoff=excluded)


class ReplayPortfolio(GoldPaperPortfolio):
    def save(self):
        pass


def replay(folder, staged, quotes, *, production_controls=False, fast_secondary_exits=False,
           scalp_priority=False,captured_lines=None):
    if production_controls:
        from run_gold_consensus_bot import _scalp_churn_blocks
    if captured_lines is None:
        captured_lines,_=freeze_capture(folder)
    observations = [json.loads(line) for line in captured_lines]
    observations = sorted((r for r in observations if 'candles' in r and 'status' in r),
                          key=lambda r: epoch(r['observed_at']))
    times = [epoch(r['observed_at']) for r in observations]
    paper = ReplayPortfolio(ROOT/'data/research/entry_efficiency/replay_accounts')
    states = {name: dict(adaptive={}, flow={}, candle={}, conscience={}, churn={}, direction='WAIT', since=0)
              for name in settings.HORIZON_PRIORITY}
    micro = MicroFlow()
    cooldown, count, skipped = 0, 0, 0
    blocked_eligible_checks={name:0 for name in settings.HORIZON_PRIORITY}
    for now, bid, ask, age, tick_time in quotes:
        if not times[0] <= now <= times[-1]:
            continue
        count += 1
        obs = observations[bisect.bisect_right(times, now)-1]
        before = len(paper.trades)
        tick_age = max(0, now-tick_time) if now-tick_time >= -settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS else float('inf')
        paper.mark(bid, ask, now, age, exit_quote_age=tick_age if production_controls else age)
        if len(paper.trades) > before:
            cooldown = now+30
            for trade in paper.trades[before:]:
                states[trade['horizon']].update(direction='WAIT', since=now, conscience={})
        if now-epoch(obs['status']['updated_at']) > 20:
            skipped += 1
            continue
        early = {}
        if production_controls:
            micro.observe(quote_time=tick_time, bid=bid, ask=ask, now=now)
            # All quote-only protection precedes any lane's entry assessment.
            for name in settings.HORIZON_PRIORITY:
                held = paper.details(name)
                flow = micro.read(held[0]['direction'] if held else None, now=now)
                protection_lane = 'SCALP' if fast_secondary_exits else name
                early[name] = quote_protection(held, states[name]['flow'], horizon=name,
                    now=now, quote_time=tick_time, bid=bid, ask=ask, flow=flow,
                    atr=obs['status']['lanes'][protection_lane].get('adaptive_market', {}).get('atr'))
                if held and early[name]['close']:
                    result = paper.close_lane(name, early[name]['reason'])
                    if result['closed_count']:
                        cooldown = now+30
                        states[name].update(direction='WAIT', since=now, conscience={})
        for name in settings.HORIZON_PRIORITY:
            data = obs['status']['lanes'][name]
            decision = dict(data['decision'])
            state, cfg = states[name], settings.HORIZON_LANES[name]
            positions = paper.details(name)
            flow = (micro.read(positions[0]['direction'] if positions else None, now=now)
                    if production_controls else dict(data.get('micro_flow', {})))
            if not production_controls and positions and flow.get('available'):
                flow.update(MicroFlow._reversal(positions[0]['direction'],
                    float(flow.get('pressure', 0)), float(flow.get('efficiency', 0)),
                    float(flow.get('acceleration', 0))))
            context = data.get('adaptive_market', {})
            if fast_secondary_exits and name != 'SCALP':
                context = dict(obs['status']['lanes']['SCALP'].get('adaptive_market', {}), horizon=name)
            protection = (early[name] if production_controls else evaluate_flow_exit(positions, state['flow'], now=now,
                quote_time=tick_time, bid=bid, ask=ask, horizon=name, atr=context.get('atr')))
            conscience = assess_position_conscience(direction=positions[0]['direction'], horizon=name,
                decision=decision, context=context, flow=protection, micro_flow=flow,
                news_risk=obs['status'].get('news_risk', {}),
                economic=obs['status'].get('economic_advisor_v5', {}).get('horizons', {}).get(name, {}),
                state=state['conscience'], now=now) if production_controls and positions else {}
            adaptive = evaluate_adaptive_exit(decision, positions, context, state['adaptive'],
                now=now, bid=bid, ask=ask, feed_age=tick_age if production_controls else age,
                config=settings.ADAPTIVE_EXIT_CONFIG[name], risk_usd=5, micro_flow=flow, conscience=conscience)
            if positions and (adaptive['close'] or protection['close']):
                result = paper.close_lane(name, adaptive['reason'] if adaptive['close'] else protection['reason'])
                if result['closed_count']:
                    cooldown = now+30
                    state.update(direction='WAIT', since=now, conscience={})
                positions = paper.details(name)
            direction = decision['direction'] if decision.get('allowed') else 'WAIT'
            if direction != state['direction']:
                state.update(direction=direction, since=now)
            blocks = confirm_next_move(decision, state['candle'], obs['candles'].get('M5'), now=now)
            blocks += entry_momentum_blocks(decision, obs['candles'].get('M1'), now=now, flow=flow)
            if production_controls and name == 'SCALP':
                reconcile(state['churn'], [t for t in paper.trades if t['horizon']==name], positions, now=now)
                blocks += reentry_blocks(state['churn'], now=now, direction=direction)
                blocks += _scalp_churn_blocks(state['churn'], now=now, spread=ask-bid, context=context)
            if name != 'SCALP':
                blocks += scalp_confirmation_blocks(decision, states['SCALP']['candle'])
            if staged:
                coordination=assess_entry_coordination(decision, paper.positions,
                    obs['candles'].get('M5'), now=now, bid=bid, ask=ask,scalp_priority=scalp_priority)
                if (coordination['blocks'] and not positions and decision.get('allowed')
                        and context.get('available') and not blocks and now>=cooldown
                        and now-state['since']>=cfg['minimum_signal_seconds']):
                    blocked_eligible_checks[name]+=1
                blocks += coordination['blocks']
            if (not positions and context.get('available') and not blocks and now >= cooldown
                    and now-state['since'] >= cfg['minimum_signal_seconds']):
                paper.open(name, decision, margin=10, stop_mode='INDIVIDUAL')
    gains = sum(max(0, t['profit']) for t in paper.trades)
    losses = -sum(min(0, t['profit']) for t in paper.trades)
    return dict(period=folder.name, staged=staged, production_controls=production_controls,
                fast_secondary_exits=fast_secondary_exits, quotes=count, stale_context_quotes=skipped,
                scalp_priority=scalp_priority,blocked_eligible_quote_checks=blocked_eligible_checks,
                entries_by_horizon={name:sum(p['horizon']==name for p in paper.trades+paper.positions)
                                    for name in settings.HORIZON_PRIORITY},
                trades=len(paper.trades), realized=round(gains-losses, 2),
                floating=round(paper.floating(), 2),
                maximum_drawdown=round(paper.max_drawdown,2),
                remaining_positions=[dict(horizon=p['horizon'],direction=p['direction'],entry_price=p['entry_price'])
                                     for p in paper.positions],
                profit_factor=round(gains/losses, 3) if losses else None,
                account_path=str(paper.root))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folders', nargs='+')
    parser.add_argument('--production-controls', action='store_true')
    parser.add_argument('--fast-secondary-exits', action='store_true')
    parser.add_argument('--output', type=Path, help='Explicit artifact path; preserves previous comparisons.')
    parser.add_argument('--start-utc',help='Exclude observations and stale status snapshots before a prospective cutoff.')
    parser.add_argument('--allow-volatility-expansion',action='store_true',
                        help='Research-only ablation of the SCALP volatility-expansion pause.')
    parser.add_argument('--scalp-priority', action='store_true',help='Stage secondary additions while allowing SCALP through this allocation gate.')
    args = parser.parse_args()
    quotes = []
    for line in (ROOT/'data/research/gold_forward/quotes_20261008.jsonl').open():
        q = json.loads(line)
        now = epoch(q['observed_at'])
        quotes.append((now, q['bid'], q['ask'], q['quote_age_seconds'],
                       q['broker_time_msc']/1000-settings.MT5_SERVER_UTC_OFFSET_SECONDS))
    quotes.sort()
    results=[]
    captured_windows={}
    for folder_name in args.folders:
        folder=Path(folder_name)
        captured_lines,capture=freeze_capture(folder,start_utc=args.start_utc)
        window_quotes=[q for q in quotes if epoch(capture['first'])<=q[0]<=epoch(capture['last'])]
        capture['quote_rows']=len(window_quotes)
        capture['quote_sha256']=hashlib.sha256(json.dumps(window_quotes,separators=(',',':')).encode()).hexdigest()
        capture['last_quote_epoch']=window_quotes[-1][0] if window_quotes else None
        captured_windows[folder.name]=capture
        with patch.object(settings,'SCALP_BLOCK_VOLATILITY_EXPANSION',
                          False if args.allow_volatility_expansion else settings.SCALP_BLOCK_VOLATILITY_EXPANSION):
            for staged in (False,True):
                results.append(replay(folder,staged,window_quotes,production_controls=args.production_controls,
                    fast_secondary_exits=args.fast_secondary_exits,scalp_priority=args.scalp_priority,
                    captured_lines=captured_lines))
    report = dict(results=results,captured_windows=captured_windows,
        research_policy=dict(allow_volatility_expansion=args.allow_volatility_expansion),
        secondary_exit_context='M1_ADAPTIVE_AND_QUOTE_PROTECTION' if args.fast_secondary_exits else 'ORIGINAL', limitations=[
        'Challenger comparison, not exact production replay or blind holdout.',
        'Recorded decisions/context update about every 15 seconds; entries use subsequent executable quotes.',
        'Independent simulated positions, candle confirmation, adaptive and flow exit states.',
        ('Includes production conscience, quote-only fast exits, own micro-flow and SCALP churn controls.'
         if args.production_controls else 'Omits production conscience and SCALP churn controls.'),
        'Current neutral-thesis exits included; recorded source-policy changes remain and warm-start positions/history are not copied.',
        '$100 simulated starting balance, assumed $10 margin per position, $.10 round-trip slippage, no fees or financing.',
        'Sampled quote stops can miss intragap touches; terminal positions are marked, not force closed.'])
    filename = 'coordination_production_controls.json' if args.production_controls else 'coordination_replay.json'
    if args.fast_secondary_exits:
        filename = 'coordination_fast_secondary_exits.json'
    output=args.output or ROOT/'data/research/entry_efficiency'/filename
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
