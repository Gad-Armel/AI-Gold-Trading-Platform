from __future__ import annotations

import argparse
import json
import threading
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import gold_consensus_settings as settings
from config import gold_inverse_settings as inverse_settings
from config import free_data_settings
from config.free_data_settings import HTTP_TIMEOUT_SECONDS, OANDA_API_TOKEN, OANDA_ENVIRONMENT, TWELVE_DATA_API_KEY
from services.bot.emergency_stop import check_emergency_stop
from services.bot.scalping_instance_lock import ScalpingInstanceAlreadyRunning, ScalpingInstanceLock
from services.dashboard.gold_unified_web import create_unified_server
from services.dashboard.gold_scalp_support import AdvisorSupport
from services.dashboard.gold_scalp_web import default_feed_directory
from services.dashboard.gold_horizon_history import load_history_resets, parsed_reset
from services.dashboard.gold_loss_reset import load_loss_reset
from services.execution.demo_session_guard import arm_demo_session, disarm_demo_session
from services.execution.gold_consensus_demo_broker import (
    close_all_consensus_positions, close_horizon_positions, execution_safety, consensus_positions, consensus_position_details,
    horizon_floating_profit, horizon_position_details, open_horizon_position,
    recent_closed_consensus_trades, session_profit,
)
from services.execution.mt5_connector import connect_mt5, disconnect_mt5
from services.market_data.oanda_gold import OandaDataError, fetch_oanda_gold_snapshot
from services.market_data.scalping_snapshot import get_scalping_snapshot, clear_scalping_candle_cache
from services.market_data.gold_broker_clock import quote_age as broker_quote_age, to_broker_time
from services.market_data.twelve_data_gold import TwelveDataError, fetch_twelve_data_snapshot
from services.market_data.free_macro_context import build_free_macro_context
from services.news.unified_news_intelligence import build_unified_news_context
from services.research.gold_advisory import build_gold_advisory
from services.research.gold_adaptive_exit import market_exit_context, evaluate_adaptive_exit
from services.research.gold_s30_execution import account_fingerprint
from services.research.gold_profit_lock import profit_lock_exit
from services.research.gold_position_conscience import assess_position_conscience
from services.research.gold_micro_flow import MicroFlow
from services.research.gold_candle_confirmation import confirm_next_move
from services.research.gold_continuous_session import session_loss_stop, post_exit_blocks
from services.research.gold_entry_momentum import entry_momentum_blocks, scalp_confirmation_blocks
from services.research.gold_entry_coordination import assess_entry_coordination
from services.research.gold_main_candle_signal import MainCandleSignal
from services.research.gold_exit_context_cache import ExitContextCache
from services.research.gold_main_event_calendar import fetch_main_calendar, load_main_calendar, validate_main_calendar
from services.research.gold_tick_history import TickHistoryBuffer
from services.research.gold_staged_m1 import staged_confirmation, execution_confirmation
from services.research.gold_s30_shadow import s30_observation
from services.research.gold_m1_quality import sequence_quality
from services.research.gold_retest_shadow import retest_observation
from services.research.gold_smc import SmcConfig, SmcStrategy, apply_smc_policy
from services.research.gold_regime_scalper import RegimeScalper
from services.research.gold_orbit_research import read_orbit_forward
from services.research.gold_multiengine_research import read_multi_research
from services.research.gold_mt5_recovery import Mt5Recovery
from services.research.gold_candle_input_health import candle_input_health, guard_candle_report
from services.research.gold_runtime_health import market_health, isolated_advisor
from services.research.gold_fast_protection import quote_protection
from services.research.gold_scalp_guard import reconcile as reconcile_scalp, reentry_blocks
from services.research.background_refresh import BackgroundRefresh
from services.research.gold_research_recorder import GoldResearchRecorder
from services.research.gold_exit_state import GoldExitStateStore
from services.research.gold_learned_policy import GoldLearnedPolicy, apply_entry_filter, learned_exit
from services.execution.gold_paper_portfolio import GoldPaperPortfolio
from services.research.gold_source_intelligence import SOURCES, fetch_source, source_status, merge_publication_risk
from services.research.gold_cross_market import CrossMarketCollector, protective_exit
from services.news.official_release_monitor import build_official_release_context
from services.market_data.gold_institutional_context import sync_gold_institutional_context_if_needed
from services.research.gold_advisory_consensus import build_gold_advisory_consensus
from services.research.gold_advisory_v2 import build_gold_advisory_v2
from services.research.gold_advisory_v3 import build_gold_advisory_v3
from services.research.gold_economic_advisor_v5 import build_gold_economic_advisor_v5
from services.research.gold_horizon_policy import (
    build_horizon_decisions, evaluate_entry_timing, should_close_horizon,
)
from services.risk.automatic_economic_calendar import sync_auto_economic_calendar_if_needed
from services.risk.news_event_filter import assess_news_event_risk
from services.utils.atomic_json import atomic_write_json


def _mark_phase(timings: dict[str, float], name: str, previous: float) -> float:
    """Observe processing stages without changing execution order or cadence."""
    current = time.perf_counter()
    timings[name] = round((current - previous) * 1000, 3)
    return current


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Independent SCALP, INTRADAY and SWING XAUUSD bot.")
    parser.add_argument("--mode", choices=("shadow", "demo"))
    parser.add_argument("--confirm", default="", help="Required only for demo execution.")
    parser.add_argument("--max-minutes", type=float, default=0.0, help="0 runs until CTRL+C.")
    parser.add_argument("--api-refresh-seconds", type=float, default=settings.API_REFRESH_SECONDS)
    parser.add_argument("--dashboard-port", type=int, default=8777)
    parser.add_argument("--no-dashboard", action="store_true")
    parser.add_argument("--exit-policy", choices=("legacy", "adaptive"), default="adaptive",
                        help="Adaptive exits use candle structure and volatility; emergency stops remain active.")
    parser.add_argument('--learned-policy', choices=('off', 'observe', 'filter'), default='off',
                        help='Experimental forecast: observe only, or veto entries and add adaptive exits.')
    parser.add_argument('--paper-trading', action='store_true',
                        help='In shadow mode, simulate a new $100 account using live MT5 quotes.')
    parser.add_argument('--cross-market-policy', choices=('observe', 'protect'), default='observe',
                        help='Experimental dollar transmission: observe, or veto entries/add corroborated exits.')
    parser.add_argument('--smc-policy', choices=('observe', 'filter'), default='observe',
                        help='XAUUSD SMC candidates: observe, or veto entries without a matching feasible setup. Never creates orders.')
    parser.add_argument('--scalp-timeframe', choices=('M1', 'S30', 'S15', 'S5', 'S1', 'AUTO', 'MICRO'), default='M1')
    parser.add_argument('--s30-cost-report', default='data/research/goldhft_20261020/s30_execution_costs.json')
    parser.add_argument('--allow-provisional-costs', action='store_true',
                        help='Explicit demo-only opt-in for an account-bound assumed cost profile.')
    parser.add_argument('--hft-paper-replay', type=Path,
                        help='Replay an observed bid/ask NPZ offline; bypasses MT5 connection and cannot place orders.')
    parser.add_argument('--hft-lookback-ms', type=int, default=250)
    parser.add_argument('--hft-entry-threshold-price', type=float, default=0.05)
    parser.add_argument('--hft-max-spread-price', type=float, default=0.60)
    parser.add_argument('--hft-assumed-latency-ms', type=int, default=10)
    parser.add_argument('--hft-holding-ms', type=int, default=500)
    parser.add_argument('--hft-max-quote-gap-ms', type=int, default=2000)
    parser.add_argument('--hft-reentry-cooldown-ms', type=int, default=500)
    parser.add_argument('--hft-max-entries-per-hour', type=int, default=60)
    parser.add_argument('--hft-round-trip-cost-price', type=float, default=0.0)
    parser.add_argument('--hft-slippage-per-side-price', type=float, default=0.0)
    args = parser.parse_args()
    if args.hft_paper_replay is None and args.mode is None:
        parser.error('--mode is required unless --hft-paper-replay is selected.')
    if args.hft_paper_replay is not None and (
        args.mode is not None or args.paper_trading or args.confirm or args.allow_provisional_costs
    ):
        parser.error('--hft-paper-replay is offline-only; remove trading mode, confirmation, and execution flags.')
    return args


def open_unified_dashboard_url(port: int) -> str:
    url = f"http://127.0.0.1:{int(port)}/"
    webbrowser.open(url)
    return url


def _run_hft_paper_replay(args: argparse.Namespace) -> int:
    from services.hft.paper_replay import load_quotes, replay

    report = replay(
        load_quotes(args.hft_paper_replay),
        lookback_ms=args.hft_lookback_ms,
        entry_threshold=args.hft_entry_threshold_price,
        max_spread=args.hft_max_spread_price,
        latency_ms=args.hft_assumed_latency_ms,
        holding_ms=args.hft_holding_ms,
        max_quote_gap_ms=args.hft_max_quote_gap_ms,
        reentry_cooldown_ms=args.hft_reentry_cooldown_ms,
        max_entries_per_hour=args.hft_max_entries_per_hour,
        round_trip_cost_price=args.hft_round_trip_cost_price,
        slippage_per_side_price=args.hft_slippage_per_side_price,
    )
    report["source"] = str(args.hft_paper_replay)
    print(json.dumps(report, indent=2))
    return 0


def _fresh_cached_v2(max_age: float) -> dict[str, Any] | None:
    try:
        report = json.loads(Path("data/runtime/gold_advisory_v2.json").read_text(encoding="utf-8"))
        stamp = datetime.fromisoformat(str(report["generated_at"]).replace("Z", "+00:00"))
        stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
        return report if 0 <= (datetime.now(timezone.utc) - stamp).total_seconds() <= max_age else None
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _fetch_v2_report() -> dict[str, Any]:
    errors: list[str] = []
    if OANDA_API_TOKEN:
        try:
            snap = fetch_oanda_gold_snapshot(OANDA_API_TOKEN, environment=OANDA_ENVIRONMENT, timeout=HTTP_TIMEOUT_SECONDS)
            return build_gold_advisory_v2(snap, data_source="OANDA v20 XAU/USD OHLC")
        except OandaDataError as error:
            errors.append(str(error))
    if TWELVE_DATA_API_KEY:
        try:
            return build_gold_advisory_v2(fetch_twelve_data_snapshot(TWELVE_DATA_API_KEY, timeout=HTTP_TIMEOUT_SECONDS))
        except TwelveDataError as error:
            errors.append(str(error))
    raise TwelveDataError(" | ".join(errors) or "No independent candle API is configured.")


def _lane_risk_usd(lane_config: dict[str, Any], positions=None, contract_size=100.0) -> float:
    """The money this lane is prepared to lose on the position: its risk unit R.

    Adaptive exits are anchored to R rather than to an ATR multiple, so a
    profit trail can never be configured to arm beyond the risk budgeted for
    the trade -- which is what made the previous trail unreachable in every
    lane once gold repriced to ~$4,270.
    """
    if str(lane_config.get('stop_mode')).upper() == 'ANALYSIS':
        actual = sum(abs(p['entry_price']-p['sl'])*p['volume']*contract_size
                     for p in (positions or []) if p.get('sl',0) > 0)
        return actual if positions else float(settings.MAX_TRADE_RISK_USD)
    if str(lane_config.get("stop_mode", "CUMULATIVE")).upper() == "INDIVIDUAL":
        value = lane_config.get("individual_stop_loss_usd")
    else:
        value = lane_config.get("cumulative_stop_loss_usd")
    if value is None:
        value = settings.INDIVIDUAL_EMERGENCY_STOP_USD
    return min(float(value), float(settings.MAX_TRADE_RISK_USD))


def _scalp_churn_blocks(lane_state: dict[str, Any], *, now: float, spread: float,
                        context: dict[str, Any]) -> list[str]:
    """Guards that make continuous scalping survivable rather than a cost bleed.

    Trading more often only helps if each trade still clears the round trip. At
    a $0.24 median spread these limits, not signal frequency, decide whether a
    high-rate scalper ends the session ahead.
    """
    blocks: list[str] = []
    recent = [t for t in lane_state.get("entry_times", []) if now - t <= 3600.0]
    lane_state["entry_times"] = recent
    hourly_limit = int(settings.SCALP_MAX_TRADES_PER_HOUR)
    if len(recent) == 30:
        blocks.append("SCALP burst guard: 30 entries in the last 30 seconds.")
    elif len(recent) >= hourly_limit:
        blocks.append(f"SCALP rate limit: {len(recent)} entries in the last hour.")
    if int(lane_state.get("consecutive_losses", 0)) >= int(settings.SCALP_MAX_CONSECUTIVE_LOSSES):
        since = now - float(lane_state.get("last_loss_at", now))
        if since < float(settings.SCALP_LOSS_COOLDOWN_SECONDS):
            blocks.append(f"SCALP loss cooldown: {int(settings.SCALP_LOSS_COOLDOWN_SECONDS - since)}s remaining.")
        else:
            lane_state["consecutive_losses"] = 0
    if not 0 <= spread <= float(settings.SCALP_MAX_SPREAD_USD):
        blocks.append(f"SCALP spread ${spread:.2f} exceeds the scalping ceiling "
                      f"${float(settings.SCALP_MAX_SPREAD_USD):.2f}.")
    if settings.SCALP_BLOCK_VOLATILITY_EXPANSION:
        regime = str(dict(context.get("structure_research", {}) or {}).get("regime", "")).upper()
        if regime == "VOLATILITY_EXPANSION":
            blocks.append("SCALP paused during volatility expansion.")
    return blocks


def _print_cycle(cycle: int, lanes: dict[str, Any], pnl: dict[str, Any], mode: str) -> None:
    print("\n" + "=" * 118)
    print(f"GOLD SCALP BOT | Cycle {cycle} | {datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z} | {mode.upper()}")
    print(f"{'LANE':<10}{'BIAS':<7}{'EVIDENCE':<10}{'ALLOWED':<9}{'OPEN':<6}{'CONVICTION':<12}{'R':<8}STATUS")
    for name, lane in lanes.items():
        if name != 'SCALP':
            continue
        d = lane["decision"]
        exit_state = lane.get("adaptive_exit") or {}
        conscience = exit_state.get("conscience") or {}
        conviction = (f"{float(conscience['conviction']):.2f}/{float(conscience['coverage']):.0%}"
                      if conscience.get("available") else "-")
        held = f"{float(exit_state['profit_r']):+.2f}R" if exit_state.get("profit_r") is not None else "-"
        print(f"{name:<10}{d['dominant_bias']:<7}{d['evidence']:<10.1f}{str(d['allowed']):<9}"
              f"{len(lane['positions']):<6}{conviction:<12}{held:<8}{lane['status']}")
    print(f"Session P/L: realized ${float(pnl.get('realized', 0)):.2f} | floating ${float(pnl.get('floating', 0)):.2f} | total ${float(pnl.get('total', 0)):.2f}")
    print("=" * 118)


def main() -> int:
    args = _arguments()
    if getattr(args, 'hft_paper_replay', None) is not None:
        return _run_hft_paper_replay(args)
    scalp_timeframe = getattr(args, 'scalp_timeframe', 'M1')
    fast_period = {'S1': 1, 'S5': 5, 'S15': 15, 'S30': 30}.get(scalp_timeframe, 30)
    fast_mode = scalp_timeframe in ('S30', 'S15', 'S5', 'S1', 'AUTO', 'MICRO')
    if fast_mode:
        from services.research.gold_s30_execution import load_costs
        if args.mode != 'demo' or args.exit_policy != 'adaptive':
            raise ValueError('Fast execution requires demo and adaptive exits')
        if not args.allow_provisional_costs:
            load_costs(args.s30_cost_report, now=time.time())
    if args.paper_trading and (args.mode != 'shadow' or args.exit_policy != 'adaptive'):
        raise ValueError('Paper trading requires --mode shadow --exit-policy adaptive')
    if args.learned_policy != 'off' and args.exit_policy != 'adaptive':
        raise ValueError('Learned policy requires --exit-policy adaptive')
    learned = GoldLearnedPolicy() if args.learned_policy != 'off' else None
    paper = None
    lock = ScalpingInstanceLock(settings.LOCK_PATH)
    dashboard_server = None
    dashboard_support = None
    dashboard_thread = None
    background = None
    source_background = None
    cross_collector = CrossMarketCollector()
    micro = MicroFlow()
    candle_signal = MainCandleSignal()
    smc = SmcStrategy(SmcConfig(**settings.SCALP_SMC_CONFIG))
    regime_scalper = RegimeScalper()
    if args.smc_policy == 'filter' and (smc.config.commission_price is None or smc.config.slippage_price is None):
        raise ValueError('SMC filter requires verified round-trip commission_price and slippage_price assumptions; use observe until configured.')
    context_cache = ExitContextCache()
    main_calendar = load_main_calendar()
    tick_history = TickHistoryBuffer()
    advisor_errors = {}
    recorder = GoldResearchRecorder() if args.exit_policy == 'adaptive' else None
    demo_armed = False
    recovery = None
    status_payload: dict[str, Any] = {}
    try:
        lock.acquire()
    except ScalpingInstanceAlreadyRunning as error:
        print(f"Bot startup blocked: {error}")
        if not args.no_dashboard:
            print(f"The bot is already running; opening the unified dashboard: {open_unified_dashboard_url(args.dashboard_port)}")
        return 1
    try:
        if not OANDA_API_TOKEN and not TWELVE_DATA_API_KEY:
            print("Independent candle API is not configured: SCALP may run from MT5 candles + tick flow; INTRADAY/SWING stay blocked.")
        terminal_path = None
        if fast_mode and args.allow_provisional_costs:
            terminal_path = json.loads(Path(args.s30_cost_report).read_text(encoding='utf-8')).get('terminal_path')
        if terminal_path:
            import MetaTrader5 as mt5
            connected = mt5.initialize(terminal_path, timeout=10000)
        else:
            connected = connect_mt5()
        if not connected:
            return 1
        import MetaTrader5 as mt5
        if learned is not None or args.paper_trading or fast_mode:
            info, account = mt5.symbol_info(settings.SYMBOL), mt5.account_info()
            if (info is None or account is None or account.currency != 'USD'
                    or abs(float(info.trade_contract_size)-100.) > .000001
                    or settings.SYMBOL != 'XAUUSD' or float(settings.LOT_SIZE) != .01):
                raise ValueError('Experimental AI/paper accounting requires USD, XAUUSD, 100oz contract, 0.01 lot.')
        if args.paper_trading:
            paper = GoldPaperPortfolio(learned_policy=args.learned_policy, cross_market_policy=args.cross_market_policy)
            print(f'Paper account: {paper.root} | new simulated balance $100')
        if fast_mode:
            costs = load_costs(args.s30_cost_report, now=time.time(),
                allow_provisional=args.allow_provisional_costs, account=mt5.account_info())
            print(f"Fast cost profile: {costs['profile_type']}; commission={costs['commission_price']}, slippage={costs['slippage_price']} price equivalents")
        if args.mode == "demo":
            armed = arm_demo_session(args.confirm, mt5.account_info(), mt5)
            if not armed.get("armed"):
                print(f"Demo startup blocked: {armed.get('reason', '')}")
                return 1
            demo_armed = True
            recovery = Mt5Recovery(mt5.account_info())
            safe, reasons = execution_safety(mt5)
            if not safe:
                print("Demo startup blocked: " + " | ".join(reasons))
                return 1
        if not args.no_dashboard:
            try:
                dashboard_directory = default_feed_directory()
                dashboard_server = create_unified_server(dashboard_directory, args.dashboard_port)
                dashboard_support = AdvisorSupport(dashboard_directory, with_advisor=True)
                dashboard_server.advisor_support = dashboard_support
                dashboard_support.start()
                dashboard_thread = threading.Thread(
                    target=dashboard_server.serve_forever,
                    kwargs={"poll_interval": 0.5},
                    daemon=True,
                    name="gold-unified-dashboard",
                )
                dashboard_thread.start()
                dashboard_url = f"http://127.0.0.1:{dashboard_server.server_address[1]}/"
                webbrowser.open(dashboard_url)
                print(f"Unified dashboard: {dashboard_url}")
            except OSError as error:
                print(f"Unified dashboard startup warning: {error}")
                print(f"Dashboard URL: {open_unified_dashboard_url(args.dashboard_port)}")

        background = BackgroundRefresh()
        source_background = BackgroundRefresh(workers=3)
        calendar_status = {"success": False, "message": "Calendar refresh pending"}
        print("\nGOLD SCALP BOT — DEMO EXECUTION ONLY")
        print("SCALP execution; higher-timeframe context analysed in the background.")
        print(f"Exit policy: {args.exit_policy.upper()}. Broker clock: UTC{settings.MT5_SERVER_UTC_OFFSET_SECONDS / 3600:+g}.")
        print(f'Capital profile: $100. Maximum {min(3,int(settings.MAX_POSITION_SLOTS))} positions total, exactly 0.01 lot per entry.')
        print("Entries use directional BIAS and evidence. Adaptive exits have no fixed profit target; protective stops remain active.")
        bound_account_fingerprint = account_fingerprint(mt5.account_info()) if args.mode == 'demo' else None
        episode_store = None
        if args.mode == 'demo' and fast_mode and (settings.EXECUTABLE_THESIS_ENABLED or settings.MARKET_AWARE_SOURCE_ENABLED):
            from services.research.gold_entry_episode_store import EntryEpisodeStore
            episode_store = EntryEpisodeStore('data/runtime/gold_entry_episodes.json', bound_account_fingerprint)
        started = time.monotonic()
        api_report = tick_report = None
        free_macro: dict[str, Any] = {}
        last_v3_fetch = -float("inf")
        api_error = ""
        state = {name: {"direction": "WAIT", "cycles": 0, "signal_since": None,
                        "exit_state": {}, "flow_exit_state": {}, "learned_exit_state": {}, "cross_exit_state": {},
                        "conscience_state": {}, "last_closed_bar": None, "previous_tickets": [],
                        "last_entry": -float("inf"), "reset_seen": "",
                        # Continuous-scalping bookkeeping: re-entry timing plus the
                        # churn guards that keep a high trade rate survivable.
                        "last_exit_at": -float("inf"), "last_exit_direction": None,
                        "entry_times": [], "consecutive_losses": 0, "last_loss_at": -float("inf"),
                        "last_execution": {"message": "No execution attempted."}} for name in settings.HORIZON_LANES}
        history_cache = {name: [] for name in settings.HORIZON_LANES}
        scalp_history = None
        exit_store = None
        if args.mode == 'demo' and args.exit_policy == 'adaptive':
            exit_store = GoldExitStateStore('data/runtime/gold_adaptive_exit_state.json',mt5.account_info())
            for name, restored in exit_store.load(time.time()).items():
                state[name].update(restored)
        last_history_fetch = -float("inf")
        cycle = 0
        last_display = -float("inf")
        previous_status_write_ms = 0.0
        from services.research.gold_context_cache import ContextCache
        analysis_cache = ContextCache()
        while args.max_minutes <= 0 or time.monotonic() - started < args.max_minutes * 60:
            cycle_started = time.monotonic()
            phase_started = time.perf_counter()
            phase_timings: dict[str, float] = {}
            try:
                snapshot = get_scalping_snapshot(settings.SYMBOL)
            except Exception as error:
                message = f'Market snapshot unavailable: {type(error).__name__}: {error}'
                status_payload.update(status='DATA_UNAVAILABLE',status_message=message,
                                      updated_at=datetime.now(timezone.utc).isoformat())
                if recovery is not None and not check_emergency_stop()[0]:
                    recovery_status = recovery.attempt(mt5, now=time.monotonic())
                    status_payload['mt5_recovery'] = recovery_status
                    if recovery_status['reconnected']:
                        clear_scalping_candle_cache()
                atomic_write_json('data/runtime/gold_consensus_status.json',status_payload,indent=2)
                if time.monotonic()-last_display >= settings.DISPLAY_INTERVAL_SECONDS:
                    print(message);last_display=time.monotonic()
                if check_emergency_stop()[0]:
                    break
                time.sleep(settings.LOOP_INTERVAL_SECONDS)
                continue
            phase_started = _mark_phase(phase_timings, 'snapshot', phase_started)
            try:
                terminal = mt5.terminal_info()
            except Exception:
                terminal = None
            health = market_health(snapshot, terminal, now=time.time())
            # Broker tick age drives PROTECTIVE exits. The stricter measure below
            # also counts seconds since the quote last CHANGED, which is a quiet
            # market rather than a broken feed, so it gates entries only.
            feed_age = broker_quote_age(float(snapshot.tick_time_msc)/1000.)
            current_quote_age = max(float(snapshot.quote_age_seconds), feed_age)
            if paper is not None:
                paper.mark(float(snapshot.bid), float(snapshot.ask), time.time(), current_quote_age,
                           exit_quote_age=feed_age)
            micro.observe(quote_time=float(snapshot.tick_time_msc)/1000.-settings.MT5_SERVER_UTC_OFFSET_SECONDS,
                          bid=float(snapshot.bid), ask=float(snapshot.ask), now=time.time())
            early_flow = {}
            early_closed = set()
            if args.exit_policy == 'adaptive':
                # Complete quote-only exit attempts before calculating any entry
                # advisor. Failed attempts retain position-bound state for retry.
                for name in settings.HORIZON_LANES:
                    held = (horizon_position_details(mt5,name) if args.mode == 'demo' else
                            paper.details(name) if paper is not None else [])
                    lane_state=state[name]
                    previous_context=status_payload.get('lanes',{}).get(name,{}).get('adaptive_market',{})
                    flow=micro.read(held[0]['direction'] if held else None,now=time.time())
                    guard=profit_lock_exit(held,lane_state['exit_state'],now=time.time(),
                        bid=float(snapshot.bid),ask=float(snapshot.ask),feed_age=feed_age,
                        config=settings.ADAPTIVE_EXIT_CONFIG[name],contract_size=float(snapshot.contract_size))
                    if not guard['close']:
                        guard=quote_protection(held,lane_state['flow_exit_state'],horizon=name,now=time.time(),
                        quote_time=float(snapshot.tick_time_msc)/1000.-settings.MT5_SERVER_UTC_OFFSET_SECONDS,
                        bid=float(snapshot.bid),ask=float(snapshot.ask),flow=flow,
                        atr=previous_context.get('atr'),contract_size=float(snapshot.contract_size))
                    early_flow[name]=guard
                    if held and guard['close']:
                        result=(close_horizon_positions(mt5,name,reason=guard['reason'],tickets=guard.get('close_tickets')) if paper is None else
                                paper.close_lane(name,guard['reason'],now=time.time(),tickets=guard.get('close_tickets')))
                        remaining=horizon_position_details(mt5,name) if paper is None else paper.details(name)
                        closed={str(p['ticket']) for p in held}-{str(p['ticket']) for p in remaining}
                        lane_state['last_execution']=dict(action='CLOSE',success=not result['failures'],
                            message=f"{name}: {guard['reason']}; closed {result['closed_count']}.")
                        if closed:
                            early_closed.add(name)
                            lane_state['pending_closed']=sorted(set(lane_state.get('pending_closed',[]))|closed)
                            lane_state['last_exit_at']=time.time()
                            lane_state['last_exit_direction']=held[0]['direction']
                            lane_state['last_entry']=time.monotonic()
                            lane_state['direction'],lane_state['cycles'],lane_state['signal_since']='WAIT',0,None
                            lane_state['conscience_state'].clear()
            phase_started = _mark_phase(phase_timings, 'quote_protection', phase_started)
            cross_market = analysis_cache.get('cross_market',
                lambda: isolated_advisor('cross_market',lambda:cross_collector.assess(mt5,snapshot),advisor_errors),
                now=time.monotonic(), ttl=1. if args.cross_market_policy == 'protect' else 5.)
            phase_started = _mark_phase(phase_timings, 'cross_market', phase_started)
            source_values = {name: source_background.poll(name, cadence,
                lambda name=name: fetch_source(name, timeout=5.), {}) for name, (_, cadence) in SOURCES.items()}
            source_intelligence = source_status(source_values, dict(source_background.errors))
            source_intelligence['cross_market'] = cross_market
            source_intelligence['cross_market_policy'] = args.cross_market_policy
            calendar_status = background.poll('calendar',3600.,
                lambda: sync_auto_economic_calendar_if_needed(free_only=True),calendar_status)
            mt5_report = analysis_cache.get('candles',
                lambda: isolated_advisor('candles',lambda:candle_signal.build(snapshot),advisor_errors),
                now=time.monotonic(), ttl=5. if fast_mode else .5)
            candle_health = candle_input_health(snapshot.candles, now=time.time(),
                offset=settings.MT5_SERVER_UTC_OFFSET_SECONDS)
            mt5_report = guard_candle_report(mt5_report, candle_health)
            phase_started = _mark_phase(phase_timings, 'source_poll_and_candles', phase_started)
            tick_cadence = float(settings.V3_REFRESH_SECONDS)
            if tick_report is None or time.monotonic() - last_v3_fetch >= tick_cadence:
                tick_report = isolated_advisor('ticks',lambda:build_gold_advisory_v3(mt5,settings.SYMBOL,history=tick_history),advisor_errors)
                tick_report['s30_shadow'] = s30_observation(tick_history.frame, now=time.time())
                last_v3_fetch = time.monotonic()
            phase_started = _mark_phase(phase_timings, 'tick_advisor', phase_started)
            cached = _fresh_cached_v2(settings.API_MAX_AGE_SECONDS)
            if cached is not None:
                api_report = cached
            fetched_api = background.poll('api', max(60.,args.api_refresh_seconds),_fetch_v2_report)
            if fetched_api is not None and (api_report is None or str(fetched_api.get('generated_at','')) > str(api_report.get('generated_at',''))):
                api_report = fetched_api
            api_error = background.errors.get('api','')
            api_for_consensus = api_report or {
                "available": False, "error": api_error or "No independent candle API report.",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source_bar_age_seconds": None, "mid": None, "horizons": {},
            }
            consensus = build_gold_advisory_consensus(mt5_report, api_for_consensus, tick_report,
                minimum_evidence=settings.MINIMUM_EVIDENCE, minimum_individual_evidence=settings.MINIMUM_INDIVIDUAL_EVIDENCE,
                lone_direction_evidence=settings.LONE_DIRECTION_EVIDENCE, maximum_mt5_age_seconds=settings.MT5_MAX_AGE_SECONDS,
                maximum_api_age_seconds=settings.API_MAX_AGE_SECONDS, maximum_tick_age_seconds=settings.V3_MAX_AGE_SECONDS,
                maximum_api_bar_age_seconds=settings.API_MAX_BAR_AGE_SECONDS,
                maximum_feed_price_difference_usd=settings.MAX_FEED_PRICE_DIFFERENCE_USD)
            phase_started = _mark_phase(phase_timings, 'consensus', phase_started)
            now_local = datetime.now()
            main_calendar = validate_main_calendar(background.poll('main_calendar',3600.,fetch_main_calendar,main_calendar))
            news_risk = assess_news_event_risk(settings.SYMBOL, now_local,
                extra_events=main_calendar.get('events',[]) if main_calendar.get('available') else [])
            official = {}
            if free_data_settings.OFFICIAL_RELEASE_MONITOR_ENABLED:
                official = background.poll('official',max(30.,free_data_settings.OFFICIAL_RELEASE_REFRESH_SECONDS),
                    lambda: build_official_release_context(cache_path=free_data_settings.OFFICIAL_RELEASE_CACHE_PATH,
                        refresh_seconds=free_data_settings.OFFICIAL_RELEASE_REFRESH_SECONDS,
                        timeout=HTTP_TIMEOUT_SECONDS,bea_api_key=free_data_settings.BEA_API_KEY,
                        census_rss_url=free_data_settings.CENSUS_ECONOMIC_RSS_URL,
                        fed_rss_url=free_data_settings.FED_MONETARY_RSS_URL),{})
            verified_events = list(official.get('events',[]) or []) + source_intelligence['events']
            news_risk = merge_publication_risk(news_risk, verified_events)
            macro = build_unified_news_context(str(snapshot.session), news_risk, datetime.now(timezone.utc),
                extra_events=verified_events)
            free_macro = background.poll('macro',3600.,lambda: build_free_macro_context(
                series=free_data_settings.FRED_SERIES,max_cache_age_seconds=3600.,
                timeout=HTTP_TIMEOUT_SECONDS,api_key=free_data_settings.FRED_API_KEY,
                include_world_bank=free_data_settings.WORLD_BANK_GEP_ENABLED),{})
            if free_data_settings.INSTITUTIONAL_AUTO_REFRESH_ENABLED:
                background.poll('institutional',max(300.,free_data_settings.INSTITUTIONAL_REFRESH_SECONDS),
                    lambda: sync_gold_institutional_context_if_needed(
                        cache_path=free_data_settings.INSTITUTIONAL_CACHE_PATH,timeout=HTTP_TIMEOUT_SECONDS,
                        max_cache_age_seconds=free_data_settings.INSTITUTIONAL_REFRESH_SECONDS,
                        cftc_app_token=free_data_settings.CFTC_SODA_APP_TOKEN))
            economic = isolated_advisor('economic',lambda:build_gold_economic_advisor_v5(macro,free_macro,snapshot=snapshot,
                institutional_path=free_data_settings.INSTITUTIONAL_CACHE_PATH),advisor_errors)
            phase_started = _mark_phase(phase_timings, 'news_macro', phase_started)
            # Completed-candle context is built before the decisions so the
            # flow-primary SCALP lane can derive its levels from live ATR.
            contexts = {name: isolated_advisor('context_'+name,
                lambda name=name:context_cache.get(snapshot,name,now_utc=datetime.now(timezone.utc)),advisor_errors)
                for name in settings.HORIZON_LANES}
            for context in contexts.values():
                context.update(bid=float(snapshot.bid), ask=float(snapshot.ask))
            decisions = build_horizon_decisions(consensus, news_risk, macro, economic,
                                                market_context=contexts)
            advisor1_scalp_decision = dict(decisions['SCALP'])
            decisions['SCALP']['setup_observation'] = dict(mt5_report.get('setup_observation', {}) or {})
            smc_report = analysis_cache.get('smc', lambda: isolated_advisor('smc', lambda: smc.assess(
                snapshot.candles, now=time.time(), bid=float(snapshot.bid), ask=float(snapshot.ask),
                offset=settings.MT5_SERVER_UTC_OFFSET_SECONDS), advisor_errors),
                now=time.monotonic(), ttl=5. if args.smc_policy == 'observe' else .5)
            decisions['SCALP']['smc_strategy'] = dict(smc_report, policy=args.smc_policy)
            phase_started = _mark_phase(phase_timings, 'exit_context_and_decisions', phase_started)
            cycle += 1
            stopped, stop_reason = check_emergency_stop()
            loss_reset = load_loss_reset()
            rolling_start = datetime.now(timezone.utc)-timedelta(hours=float(settings.LOSS_LOOKBACK_HOURS))
            pnl_started = max(rolling_start, loss_reset) if loss_reset else rolling_start
            pnl = (session_profit(mt5, pnl_started) if args.mode == 'demo' else
                   paper.pnl(pnl_started.timestamp()) if paper is not None else
                   {"available": True, "realized": 0, "floating": 0, "total": 0})
            loss_stop = session_loss_stop(pnl)
            resets = load_history_resets()
            refresh_history = time.monotonic() - last_history_fetch >= float(settings.TRADE_HISTORY_REFRESH_SECONDS)
            history_snapshot = None
            history_refresh_ms = 0.0
            if args.mode == 'demo' and (refresh_history or any(
                    resets.get(name, '') != state[name]['reset_seen'] for name in settings.HORIZON_LANES)):
                history_started = time.monotonic()
                history_now = datetime.now(timezone.utc)
                try:
                    history_snapshot = mt5.history_deals_get(
                        to_broker_time(history_now-timedelta(days=30)), to_broker_time(history_now))
                except Exception:
                    history_snapshot = None
                history_refresh_ms = (time.monotonic()-history_started)*1000
            if args.mode == 'demo' and (refresh_history or scalp_history is None):
                try:
                    scalp_history = recent_closed_consensus_trades(mt5, limit=1000, lookback_days=2,
                        magic_number=int(settings.HORIZON_LANES['SCALP']['magic']), strict=True)
                except Exception:
                    scalp_history = None
            phase_started = _mark_phase(phase_timings, 'account_history', phase_started)
            if fast_mode:
                from services.research.gold_s30_execution import refresh_fast_snapshot, directional_signal
                snapshot, fast_tick_health = refresh_fast_snapshot(mt5, tick_history, snapshot)
                tick_report['history_health'] = fast_tick_health
                health = market_health(snapshot, mt5.terminal_info(), now=time.time())
                contexts['SCALP'].update(bid=float(snapshot.bid), ask=float(snapshot.ask))
                timeframe_selection = None
                if args.scalp_timeframe in ('AUTO', 'MICRO'):
                    from services.research.gold_fast_selection import select_period, candidate_risk_blocks
                    existing = horizon_position_details(mt5, 'SCALP')
                    held_period = state['SCALP'].get('entry_period_seconds', 30) if existing else None
                    fast_period, timeframe_selection = select_period(tick_history.frame, now=time.time(),
                        bid=float(snapshot.bid), ask=float(snapshot.ask), atr=contexts['SCALP'].get('atr', 0.),
                        cost_path=args.s30_cost_report, account=mt5.account_info(),
                        allow_provisional=args.allow_provisional_costs, held_period=held_period,
                        include_s1=args.scalp_timeframe == 'MICRO',
                        risk_evaluator=lambda signal: candidate_risk_blocks(mt5, signal,
                            bid=float(snapshot.bid), ask=float(snapshot.ask)))
                s30_signal = directional_signal(tick_history.frame, now=time.time(),
                    bid=float(snapshot.bid), ask=float(snapshot.ask), atr=contexts['SCALP'].get('atr', 0.),
                    period_seconds=fast_period, bar_count=settings.FAST_CONFIRMATION_BARS)
                decisions['SCALP'] = build_horizon_decisions(consensus, news_risk, macro, economic,
                    market_context=contexts, scalp_signal=s30_signal)['SCALP']
                decisions['SCALP']['advisor1_context'] = dict(direction=advisor1_scalp_decision.get('direction'),
                    evidence=advisor1_scalp_decision.get('evidence'), role='CONTEXT_ONLY')
                decisions['SCALP']['smc_strategy'] = dict(smc_report, policy=args.smc_policy)
                decisions['SCALP']['fast_timeframe_selection'] = timeframe_selection
                decisions['SCALP']['setup_observation'] = dict(mt5_report.get('setup_observation', {}) or {})
                if not fast_tick_health.get('available'):
                    decisions['SCALP']['allowed'] = False
                    decisions['SCALP']['blocks'].append(fast_tick_health.get('error') or 'Fresh tick history unavailable')
            phase_started = _mark_phase(phase_timings, 'fast_entry_refresh', phase_started)
            if fast_mode and settings.THREE_SOURCE_VOTE_ENABLED:
                from services.research.gold_source_vote import source_vote
                decisions['SCALP'] = source_vote(decisions['SCALP'], contexts['SCALP'], now=time.time(),
                    maximum=min(3, int(settings.MAX_POSITION_SLOTS)))
                if settings.EXECUTABLE_THESIS_ENABLED or settings.EXECUTABLE_THESIS_SHADOW_ENABLED:
                    from services.research.gold_execution_thesis import execution_thesis
                    thesis = execution_thesis(tick_history.frame, now=time.time(),
                        direction=decisions['SCALP']['direction'], atr=contexts['SCALP'].get('atr',0.),
                        commission=costs['commission_price'], slippage=costs['slippage_price'])
                    thesis_blocks = list(thesis['blocks'])
                    if not fast_tick_health.get('available'):
                        thesis_blocks.append(fast_tick_health.get('error') or 'Tick input unavailable.')
                    if episode_store is not None:
                        episode_store.reconcile(mt5, now=time.time())
                        if thesis.get('setup_id'):
                            thesis_blocks.extend(episode_store.blocks(thesis['setup_id'], thesis['direction']))
                        thesis['episode_ledger'] = episode_store.status()
                    if settings.EXECUTABLE_THESIS_ENABLED:
                        if thesis_blocks:
                            decisions['SCALP']['allowed'] = False
                            decisions['SCALP']['blocks'].extend(thesis_blocks)
                        elif thesis.get('allowed'):
                            levels=thesis['levels']
                            decisions['SCALP'].update(levels=levels, stop_loss=levels['sl'],
                                take_profit=levels['tp1'], entry_reference=levels['entry_reference'])
                    thesis.update(execution_enabled=settings.EXECUTABLE_THESIS_ENABLED,
                                  role='ENTRY_FILTER' if settings.EXECUTABLE_THESIS_ENABLED else 'SHADOW_ONLY')
                    decisions['SCALP']['execution_thesis'] = thesis
                if settings.MARKET_AWARE_SOURCE_ENABLED:
                    from services.research.gold_market_entry_plan import market_entry_plan
                    plan = market_entry_plan(tick_history.frame, contexts['SCALP'], now=time.time(),
                        direction=decisions['SCALP']['direction'], commission=costs['commission_price'],
                        slippage=costs['slippage_price'], maximum_risk=settings.MAX_TRADE_RISK_USD)
                    plan_blocks = list(plan['blocks'])
                    if not fast_tick_health.get('available'):
                        plan_blocks.append(fast_tick_health.get('error') or 'Tick input unavailable.')
                    if episode_store is not None:
                        episode_store.reconcile(mt5, now=time.time())
                        if plan.get('setup_id'):
                            plan_blocks.extend(episode_store.blocks(plan['setup_id'], plan['direction']))
                        plan['episode_ledger'] = episode_store.status()
                    if plan_blocks:
                        decisions['SCALP']['allowed'] = False
                        decisions['SCALP']['blocks'].extend(plan_blocks)
                    elif plan['allowed']:
                        levels=plan['levels']
                        decisions['SCALP'].update(levels=levels, stop_loss=levels['sl'],
                            take_profit=levels['tp1'], entry_reference=levels['entry_reference'])
                    plan.update(execution_enabled=True, blocks=plan_blocks)
                    decisions['SCALP']['market_entry_plan'] = plan
            from services.research.gold_market_schedule import market_schedule, execution_plan
            decisions['SCALP']['market_schedule'] = market_schedule()
            decisions['SCALP']['market_execution_plan'] = execution_plan(decisions['SCALP'])
            regime_observation = isolated_advisor('regime_research', lambda: regime_scalper.assess(
                tick_history.frame, snapshot.candles, now=time.time(), bid=float(snapshot.bid),
                ask=float(snapshot.ask), offset=settings.MT5_SERVER_UTC_OFFSET_SECONDS), advisor_errors)
            decisions['SCALP']['regime_research'] = dict(regime_observation,
                role='FORWARD_RESEARCH_ONLY', execution_enabled=False,
                validation='Historical comparison did not demonstrate positive expectancy after costs')
            decisions['SCALP']['orbit_research'] = read_orbit_forward(now=time.time())
            decisions['SCALP']['multi_engine_research'] = read_multi_research(now=time.time())
            lanes: dict[str, Any] = {}
            # Priority order, not dictionary order: when the global three-slot
            # cap binds, SCALP is considered first. This ordering does not
            # override per-entry risk, margin, freshness or cost checks.
            ordered = [n for n in settings.HORIZON_PRIORITY if n in decisions]
            ordered += [n for n in decisions if n not in ordered]
            for name in ordered:
                decision = decisions[name]
                if name == 'SCALP':
                    decision['candle_input_health'] = candle_health
                lane_state = state[name]
                if stopped or loss_stop or not pnl.get("available", True):
                    decision["allowed"] = False
                    decision["blocks"].append(stop_reason if stopped else "Session risk circuit breaker is active.")
                positions = horizon_position_details(mt5, name) if args.mode == "demo" else paper.details(name) if paper is not None else []
                exit_context = contexts.get(name, {}) if args.exit_policy == "adaptive" else {}
                held_direction = positions[0]["direction"] if positions else None
                if not positions:
                    lane_state.pop('fast_reversal_state', None)
                flow_read = micro.read(held_direction, now=time.time())
                exit_decision = {}
                from services.research.gold_s30_execution import position_exit_signal
                reversal = dict(close=False)
                if name == 'SCALP' and fast_mode and positions and decision.get('entry_mode') != 'THREE_SOURCE_VOTE':
                    from services.research.gold_s30_execution import entry_check, confirmed_fast_reversal
                    from services.research.gold_fast_selection import select_period, candidate_risk_blocks
                    from services.research.gold_s30_execution import directional_signal
                    opposite = 'SELL' if held_direction == 'BUY' else 'BUY'
                    reverse_period, reverse_selection = select_period(tick_history.frame,
                        now=time.time(), bid=float(snapshot.bid), ask=float(snapshot.ask),
                        atr=float(exit_context.get('atr', 0)), cost_path=args.s30_cost_report,
                        account=mt5.account_info(), allow_provisional=args.allow_provisional_costs,
                        required_direction=opposite,
                        risk_evaluator=lambda signal: candidate_risk_blocks(mt5, signal,
                            bid=float(snapshot.bid), ask=float(snapshot.ask)))
                    reverse_signal = directional_signal(tick_history.frame, now=time.time(),
                        bid=float(snapshot.bid), ask=float(snapshot.ask), atr=float(exit_context.get('atr', 0)),
                        period_seconds=reverse_period, bar_count=settings.FAST_CONFIRMATION_BARS)
                    reverse_decision = dict(decision, direction=reverse_signal['bias'],
                        entry_mode=f'S{reverse_period}_PRIMARY',
                        allowed=any(c['eligible'] for c in reverse_selection['candidates']))
                    reversal_blocks, _ = entry_check(reverse_decision, tick_history.frame,
                        now=time.time(), plan=dict(required_bars=settings.FAST_CONFIRMATION_BARS, after_epoch=None),
                        cost_path=args.s30_cost_report, period_seconds=reverse_period,
                        allow_provisional=args.allow_provisional_costs, account=mt5.account_info())
                    reversal = confirmed_fast_reversal(reverse_decision, held_direction,
                        lane_state.setdefault('fast_reversal_state', {}), now=time.monotonic(),
                        entry_blocks=reversal_blocks,
                        position_ids=[p['ticket'] for p in positions], require_fresh_quotes=True,
                        quote_time=float(snapshot.tick_time_msc)/1000-settings.MT5_SERVER_UTC_OFFSET_SECONDS,
                        market_available=bool(health['available']) and not stopped and not loss_stop
                            and not Path('data/runtime/gold_entry_research_hold.flag').exists())
                    reversal['selection'] = reverse_selection
                elif name == 'SCALP' and decision.get('entry_mode') != 'THREE_SOURCE_VOTE':
                    lane_state.pop('fast_reversal_state', None)
                if positions and decision.get('entry_mode') == 'THREE_SOURCE_VOTE':
                    from services.research.gold_s30_execution import confirmed_fast_reversal
                    reversal_blocks = []
                    if not flow_read.get('available') or flow_read.get('bias') != decision.get('direction'):
                        reversal_blocks.append('Fresh executable flow must confirm the opposite source vote.')
                    reversal = confirmed_fast_reversal(decision, held_direction,
                        lane_state.setdefault('fast_reversal_state', {}), now=time.monotonic(), entry_blocks=reversal_blocks,
                        position_ids=[p['ticket'] for p in positions], require_fresh_quotes=True,
                        quote_time=float(snapshot.tick_time_msc)/1000-settings.MT5_SERVER_UTC_OFFSET_SECONDS,
                        market_available=bool(health['available']) and not stopped and not loss_stop
                            and not Path('data/runtime/gold_entry_research_hold.flag').exists())
                decision['fast_reversal'] = reversal
                decision['cross_market'] = cross_market
                if (args.cross_market_policy == 'protect' and cross_market.get('available')
                        and cross_market.get('gold_bias') in ('BUY', 'SELL')
                        and decision.get('direction') in ('BUY', 'SELL')
                        and cross_market['gold_bias'] != decision['direction']):
                    decision['allowed'] = False
                    decision['blocks'].append('Experimental dollar-transmission contradiction.')
                assessment = isolated_advisor('learned_'+name,lambda:learned.assess(snapshot,name,exit_context),advisor_errors) if learned is not None else {}
                if args.learned_policy == 'filter':
                    apply_entry_filter(decision, assessment)
                elif learned is not None:
                    decision['learned_policy'] = assessment
                if not health['available']:
                    decision['allowed'] = False
                    decision['blocks'] = health['entry_blocks'] + decision['blocks']
                if not decision.get('allowed'):
                    reversal['close'] = False
                    lane_state.pop('fast_reversal_state', None)
                exit_signal = position_exit_signal(decision,
                    confirmed_reversal=reversal['close'] if name == 'SCALP' and fast_mode else None)
                if lane_state['previous_tickets'] and not positions:
                    lane_state['pending_closed'] = sorted(set(lane_state.get('pending_closed', []))
                        | {str(t) for t in lane_state['previous_tickets']})
                    lane_state['last_exit_at'] = time.time()
                    lane_state['conscience_state'].clear()
                    lane_state['last_closed_bar'] = exit_context.get('bar_id')
                    lane_state['last_entry'] = time.monotonic()
                    lane_state['direction'],lane_state['cycles'],lane_state['signal_since'] = 'WAIT',0,None
                closed_this_cycle = name in early_closed
                if (args.mode == "demo" or paper is not None) and positions:
                    lane_profit = horizon_floating_profit(mt5, name) if paper is None else {'available': True, 'profit': paper.floating(name)}
                    target_hit = (lane_profit.get("available", False)
                                  and args.exit_policy == "legacy"
                                  and float(lane_profit.get("profit", 0.0))
                                  >= float(settings.HORIZON_CUMULATIVE_TAKE_PROFIT_USD))
                    cfg = settings.HORIZON_LANES[name]
                    cumulative_sl = cfg.get("cumulative_stop_loss_usd")
                    stop_hit = (cumulative_sl is not None and lane_profit.get("available", False)
                                and float(lane_profit.get("profit", 0.0)) <= -float(cumulative_sl))
                    close_needed, reason = should_close_horizon(decision, positions[0]["direction"])
                    if args.exit_policy == "adaptive":
                        # Flow first: the conscience reads it, and the adaptive
                        # exit sizes its giveback from the conscience.
                        flow_exit = early_flow.get(name,{})
                        conscience = assess_position_conscience(
                            direction=positions[0]['direction'], horizon=name, decision=exit_signal,
                            context=exit_context, flow=flow_exit,
                            cross_market=cross_market if args.cross_market_policy == 'protect' else {},
                            learned=assessment if args.learned_policy == 'filter' else {},
                            news_risk=news_risk, micro_flow=flow_read,
                            economic=dict(economic.get('horizons', {}).get(name, {}) or {}),
                            state=lane_state['conscience_state'], now=time.time(),
                        ) if settings.CONSCIENCE_ENABLED else {}
                        exit_decision = evaluate_adaptive_exit(exit_signal, positions, exit_context,
                            lane_state['exit_state'], now=time.time(), bid=float(snapshot.bid),
                            ask=float(snapshot.ask), feed_age=broker_quote_age(float(snapshot.tick_time_msc)/1000.),
                            config=settings.ADAPTIVE_EXIT_CONFIG[name],
                            risk_usd=_lane_risk_usd(cfg, positions, float(snapshot.contract_size)), contract_size=float(snapshot.contract_size),
                            conscience=conscience, micro_flow=flow_read)
                        close_needed, reason = exit_decision['close'], exit_decision['reason']
                        exit_decision['quote_flow'] = flow_exit
                        exit_decision['signal_source'] = exit_signal['exit_thesis_source']
                        exit_decision['conscience'] = conscience
                        if flow_exit.get('close') and not close_needed:
                            close_needed, reason = True, flow_exit['reason']
                            exit_decision.update(close=True, reason=reason)
                        if args.cross_market_policy == 'protect' and protective_exit(cross_market, positions,
                                exit_context, lane_state['cross_exit_state'], feed_age) and not close_needed:
                            close_needed, reason = True, 'Dollar contradiction and gold deterioration on two completed candles'
                            exit_decision.update(close=True, reason=reason, cross_market=True)
                        if args.learned_policy == 'filter' and learned_exit(assessment, positions,
                                lane_state['learned_exit_state'], feed_age) and not close_needed:
                            close_needed, reason = True, 'Learned continuation forecast adverse on two completed candles'
                            exit_decision.update(close=True, reason=reason, learned=True)
                    if reversal['close']:
                        close_needed, reason = True, reversal['reason']
                        exit_decision.pop('close_tickets', None)
                        exit_decision.update(close=True, reason=reason)
                    if stopped or loss_stop:
                        close_needed, reason = True, 'Global risk circuit breaker'
                    if target_hit:
                        close_needed = True
                        reason = (f"cumulative TP reached: ${float(lane_profit['profit']):.2f}"
                                  f" >= ${settings.HORIZON_CUMULATIVE_TAKE_PROFIT_USD:.2f}")
                    elif stop_hit:
                        close_needed = True
                        reason = (f"cumulative SL reached: ${float(lane_profit['profit']):.2f}"
                                  f" <= -${float(cumulative_sl):.2f}")
                    if close_needed:
                        closing_direction = positions[0]["direction"] if positions else None
                        closing_tickets = {str(p['ticket']) for p in positions}
                        tickets = exit_decision.get('close_tickets') if args.exit_policy == 'adaptive' and reason == exit_decision['reason'] else None
                        result = close_horizon_positions(mt5, name, reason=reason, tickets=tickets) if paper is None else paper.close_lane(name, reason, now=time.time(), tickets=tickets)
                        lane_state["last_execution"] = {"action": "CLOSE", "success": not result["failures"], "message": f"{name}: {reason}; closed {result['closed_count']}."}
                        positions, closed_this_cycle = (horizon_position_details(mt5, name) if paper is None else paper.details(name)), True
                        lane_state['last_closed_bar'] = exit_context.get('bar_id')
                        lane_state['last_entry'] = time.monotonic()
                        actually_closed = closing_tickets - {str(p['ticket']) for p in positions}
                        if actually_closed:
                            lane_state['pending_closed'] = sorted(set(lane_state.get('pending_closed', [])) | actually_closed)
                            lane_state['last_exit_at'] = time.time()
                            lane_state['last_exit_direction'] = closing_direction
                            lane_state['conscience_state'].clear()
                        lane_state['direction'], lane_state['cycles'], lane_state['signal_since'] = 'WAIT', 0, None
                if not positions:
                    lane_state['exit_state'].clear()
                    lane_state['flow_exit_state'].clear()
                    lane_state['learned_exit_state'].clear()
                    lane_state['cross_exit_state'].clear()
                lane_profit = (horizon_floating_profit(mt5, name) if args.mode == 'demo' else
                               {'available': True, 'profit': paper.floating(name), 'position_count': len(positions)} if paper is not None else
                               {"available": True, "profit": 0.0, "position_count": 0})
                if name == 'SCALP':
                    apply_smc_policy(decision, smc_report, policy=args.smc_policy, now=time.time())
                    if Path('data/runtime/gold_entry_research_hold.flag').exists():
                        decision['allowed'] = False
                        decision['blocks'].append('Research entry hold: position exits and broker stops remain active.')
                direction = decision["direction"] if decision["allowed"] else "WAIT"
                timing_now = time.monotonic()
                from services.research.gold_signal_persistence import update_signal_persistence
                update_signal_persistence(lane_state, direction=direction,
                    source=decision.get('entry_mode'), now=timing_now)
                cfg = settings.HORIZON_LANES[name]
                if name == 'SCALP':
                    fills = ([t for t in paper.trades if t['horizon'] == name] if paper is not None else
                             scalp_history if args.mode == 'demo' else [])
                    reconcile_scalp(lane_state, fills, positions, now=time.time())
                signal_age = (timing_now - float(lane_state["signal_since"])
                              if lane_state["signal_since"] is not None else 0.0)
                timing_ready, timing_blocks = evaluate_entry_timing(
                    decision, open_position_count=len(positions), signal_age_seconds=signal_age,
                    seconds_since_last_entry=timing_now - float(lane_state["last_entry"]),
                    lane_config=cfg,
                )
                lane_state.setdefault('candle_confirmation_state', {})
                candle_blocks = [] if name == 'SCALP' and fast_mode else confirm_next_move(
                    decision, lane_state.setdefault('candle_confirmation_state', {}),
                    snapshot.candles.get('M1' if name == 'SCALP' else 'M5'), now=time.time(),
                    frame='M1' if name == 'SCALP' else 'M5',
                    required_bars=settings.SCALP_M1_CONFIRMATION_BARS if name == 'SCALP' else 2)
                decision['candle_confirmation'] = dict(lane_state['candle_confirmation_state'].get('confirmation', {}))
                if candle_blocks:
                    timing_ready = False
                    timing_blocks.extend(candle_blocks)
                pause_blocks = post_exit_blocks(state, now=time.time())
                if pause_blocks:
                    timing_ready = False
                    timing_blocks.extend(pause_blocks)
                if name in ('SCALP', 'INTRADAY', 'SWING'):
                    staged = staged_confirmation(positions) if name == 'SCALP' else dict(required_bars=1, after_epoch=None)
                    if name == 'SCALP' and fast_mode:
                        from services.research.gold_staged_m1 import fast_confirmation
                        staged = fast_confirmation(staged)
                    active = execution_confirmation(staged, scalp=name == 'SCALP')
                    momentum_blocks = entry_momentum_blocks(decision, snapshot.candles.get('M1'),
                                                           now=time.time(), flow=flow_read,
                                                           required_bars=active['required_bars'],
                                                           after_epoch=active['after_epoch'])
                    if name == 'SCALP' and fast_mode:
                        from services.research.gold_s30_execution import entry_check
                        momentum_blocks, s30_active = entry_check(decision, tick_history.frame,
                            now=time.time(), plan=staged, cost_path=args.s30_cost_report, period_seconds=fast_period,
                            allow_provisional=args.allow_provisional_costs, account=mt5.account_info())
                        lane_state.setdefault('candle_confirmation_state', {})['confirmation'] = dict(
                            frame=f'S{fast_period}', required_bars=staged['required_bars'], waiting=bool(momentum_blocks))
                        decision['candle_confirmation'] = dict(lane_state['candle_confirmation_state']['confirmation'])
                        decision['s30_entry'] = s30_active
                    decision['entry_timeframe'] = f'S{fast_period}' if name == 'SCALP' and fast_mode else 'M1'
                    decision['m1_entry_confirmation_required_bars'] = active['required_bars']
                    if name == 'SCALP':
                        decision['m1_sequence_quality'] = sequence_quality(snapshot.candles.get('M1'),
                            now=time.time(), direction=decision.get('direction'), bid=float(snapshot.bid),
                            ask=float(snapshot.ask), atr=exit_context.get('atr', 0),
                            required_bars=active['required_bars'], offset=settings.MT5_SERVER_UTC_OFFSET_SECONDS)
                        decision['m1_retest_shadow'] = retest_observation(snapshot.candles.get('M1'),
                            now=time.time(), direction=decision.get('direction'), atr=exit_context.get('atr', 0),
                            offset=settings.MT5_SERVER_UTC_OFFSET_SECONDS)
                        decision['staged_m1_observation'] = dict(staged,
                            execution_enabled=settings.SCALP_STAGED_M1_ENABLED,
                            blocks=entry_momentum_blocks(decision, snapshot.candles.get('M1'), now=time.time(),
                                flow=flow_read, required_bars=staged['required_bars'], after_epoch=staged['after_epoch']))
                        decision['s30_shadow'] = dict((tick_report or {}).get('s30_shadow', {}))
                    if decision.get('entry_mode') == 'THREE_SOURCE_VOTE':
                        from services.research.gold_s30_execution import load_costs
                        momentum_blocks = []
                        try:
                            load_costs(args.s30_cost_report, now=time.time(),
                                allow_provisional=args.allow_provisional_costs, account=mt5.account_info())
                        except (OSError, ValueError, KeyError, TypeError) as error:
                            momentum_blocks = [f'Cost profile: {error}']
                        decision['entry_timeframe'] = 'THREE_SOURCE_VOTE'
                    decision['entry_momentum_blocks'] = momentum_blocks
                    if momentum_blocks:
                        timing_ready = False
                        timing_blocks.extend(momentum_blocks)
                if name in ('INTRADAY', 'SWING'):
                    leading_blocks = scalp_confirmation_blocks(decision,
                        state.get('SCALP', {}).get('candle_confirmation_state', {}))
                    if leading_blocks:
                        timing_ready = False
                        timing_blocks.extend(leading_blocks)
                # Preserve SCALP access while staging secondary same-direction
                # exposure. Refresh per lane so an earlier fill in this cycle
                # is included in the next lane's allocation assessment.
                coordination_positions = (consensus_position_details(mt5) if args.mode == 'demo'
                                          else paper.positions if paper is not None else [])
                coordination_mode = str(settings.ENTRY_COORDINATION_MODE).upper()
                decision['entry_coordination'] = assess_entry_coordination(
                    decision, coordination_positions, snapshot.candles.get('M5'),
                    now=time.time(), bid=float(snapshot.bid), ask=float(snapshot.ask),
                    scalp_priority=coordination_mode == 'SCALP_PRIORITY')
                decision['entry_coordination']['mode'] = coordination_mode
                decision['entry_coordination']['enforced'] = coordination_mode == 'SCALP_PRIORITY'
                if coordination_mode == 'SCALP_PRIORITY' and not decision['entry_coordination']['allowed']:
                    timing_ready = False
                    timing_blocks.extend(decision['entry_coordination']['blocks'])
                if len(coordination_positions) >= min(3, int(settings.MAX_POSITION_SLOTS)):
                    timing_ready = False
                    timing_blocks.append(f'Global limit: {settings.MAX_POSITION_SLOTS} positions total across all horizons.')
                if args.exit_policy == 'adaptive':
                    if not exit_context.get('available'):
                        timing_ready = False
                        timing_blocks.append('Adaptive entry requires completed candles.')
                    elif str(cfg.get('entry_mode', '')).upper() in ('FLOW_PRIMARY', 'ADVISOR1_PRIMARY'):
                        # A scalper must be able to act on the next flow reading,
                        # including in the opposite direction. Waiting for a new
                        # completed bar would idle the lane for a whole bar after
                        # every exit -- five minutes on M5, which is longer than
                        # the trade itself.
                        churn = reentry_blocks(lane_state, now=time.time(), direction=direction)
                        churn += _scalp_churn_blocks(lane_state, now=time.time(),
                                                    spread=float(snapshot.spread), context=exit_context)
                        if (str(cfg.get('entry_mode', '')).upper() == 'FLOW_PRIMARY'
                                and (not flow_read.get('available') or flow_read.get('bias') != direction)):
                            churn.append('SCALP requires fresh micro-flow agreeing with entry direction.')
                        if churn:
                            timing_ready = False
                            timing_blocks.extend(churn)
                    elif (not settings.CONTINUOUS_DIRECTIONAL_ENTRIES
                          and lane_state['last_closed_bar'] == exit_context.get('bar_id')):
                        timing_ready = False
                        timing_blocks.append('Adaptive entry requires fresh completed candles after the last exit.')
                    if positions and name == 'SCALP':
                        from services.research.gold_scalp_additions import addition_blocks
                        additions = addition_blocks(decision, positions, float(snapshot.bid), float(snapshot.ask))
                        timing_blocks.extend(additions)
                        if additions:
                            timing_ready = False
                    elif positions and decision.get('entry_mode') != 'THREE_SOURCE_VOTE':
                        timing_ready = False
                        timing_blocks.append('Adaptive candidate uses one position per lane until pyramiding is validated.')
                attempted_entry = False
                if decision.get('entry_mode') == 'THREE_SOURCE_VOTE':
                    if len(positions) >= decision.get('source_position_limit', 0):
                        timing_ready = False
                        timing_blocks.append('Strong-source position allowance reached.')
                    if any(p['direction'] != decision.get('direction') for p in positions):
                        timing_ready = False
                        timing_blocks.append('Close opposite positions before source-vote entry.')
                entry_result = None
                if ((args.mode == "demo" or paper is not None) and not closed_this_cycle and decision["allowed"]
                        and timing_ready
                        and len(positions) < int(cfg["max_positions"])
                        and time.monotonic() - lane_state["last_entry"] >= float(settings.MINIMUM_ENTRY_SPACING_SECONDS)):
                    decision['entry_observation'] = dict(
                        checked_at=datetime.now(timezone.utc).isoformat(),
                        signal_age_seconds=signal_age,
                        required_m1_bars=decision.get('m1_entry_confirmation_required_bars', 1),
                        staged_m1_enabled=settings.SCALP_STAGED_M1_ENABLED,
                        open_positions=len(positions),
                        market_health=health,
                        micro_flow=flow_read,
                        confirmation=dict(lane_state.get('candle_confirmation_state', {}).get('confirmation', {})),
                        timing_blocks=list(timing_blocks))
                    if paper is None:
                        active_episode = (decision.get('market_entry_plan') or decision.get('execution_thesis', {})).get('setup_id') if name == 'SCALP' else None
                        if episode_store is not None and active_episode:
                            episode_store.reserve(active_episode, decision['direction'], now=time.time())
                        result = open_horizon_position(mt5, name, decision)
                        if episode_store is not None and active_episode:
                            episode_store.acknowledge(active_episode, decision['direction'], result)
                    else:
                        order_type = mt5.ORDER_TYPE_BUY if decision['direction'] == 'BUY' else mt5.ORDER_TYPE_SELL
                        price = float(snapshot.ask) if decision['direction'] == 'BUY' else float(snapshot.bid)
                        margin = mt5.order_calc_margin(order_type, settings.SYMBOL, .01, price)
                        info = mt5.symbol_info(settings.SYMBOL)
                        if info is None:
                            margin = None
                        result = paper.open(name, decision, margin=margin, stop_mode=cfg['stop_mode'],
                            now=time.time(),
                            minimum_stop_distance=float(info.trade_stops_level)*float(info.point) if info is not None else 0.)
                    attempted_entry, entry_result = True, result
                    lane_state["last_execution"] = result
                    if result["success"]:
                        lane_state["last_entry"] = time.monotonic()
                    else:
                        # Signal timing can be ready while broker-side cost,
                        # level or order checks reject execution. Publish that
                        # outcome so READY never hides a current failed attempt.
                        timing_ready = False
                        timing_blocks.append(str(result.get('message') or result.get('action') or
                                                 'Entry execution was not accepted.'))
                    positions = horizon_position_details(mt5, name) if paper is None else paper.details(name)
                    if result['success']:
                        if name == 'SCALP' and fast_mode:
                            lane_state['entry_period_seconds'] = fast_period
                        for position in positions:
                            lane_state.setdefault('entry_events', {}).setdefault(str(position['ticket']), time.time())
                        lane_state['entry_times'] = list(lane_state['entry_events'].values())
                if name == 'SCALP':
                    from services.research.gold_trigger_funnel import observe_funnel
                    from services.research.gold_graded_trigger import graded_trigger
                    from services.research.gold_trigger_labels import observe_labels
                    decision['trigger_funnel'] = observe_funnel(lane_state.setdefault('trigger_funnel_state', {}),
                        decision, timing_blocks=timing_blocks, attempted=attempted_entry, result=entry_result)
                    decision['graded_trigger'] = graded_trigger(decision, exit_context, flow_read,
                        bid=float(snapshot.bid), ask=float(snapshot.ask))
                    decision['counterfactual_labels'] = observe_labels(
                        lane_state.setdefault('trigger_label_state', {}), decision, now=time.time(),
                        bid=float(snapshot.bid), ask=float(snapshot.ask),
                        feed_age=broker_quote_age(float(snapshot.tick_time_msc)/1000.), attempted=attempted_entry)
                reset_changed = resets.get(name, "") != lane_state["reset_seen"]
                if args.mode == "demo" and (refresh_history or reset_changed):
                    history_cache[name] = recent_closed_consensus_trades(mt5, limit=settings.HORIZON_HISTORY_LIMIT,
                        magic_number=int(cfg["magic"]), reset_after=parsed_reset(resets.get(name, "")),
                        deals_snapshot=history_snapshot)
                    lane_state["reset_seen"] = resets.get(name, "")
                history = history_cache[name] if args.mode == "demo" else list(reversed([t for t in paper.trades if t['horizon'] == name][-settings.HORIZON_HISTORY_LIMIT:])) if paper is not None else []
                lane_state['previous_tickets'] = [p['ticket'] for p in positions]
                profit_cfg = settings.ADAPTIVE_EXIT_CONFIG[name]
                for position in positions:
                    peak = lane_state['exit_state'].get('ticket_profit_peaks', {}).get(str(position['ticket']))
                    if peak is not None and profit_cfg.get('profit_lock_arm_usd'):
                        armed = peak >= float(profit_cfg['profit_lock_arm_usd'])
                        position['peak_profit_usd'] = round(peak, 2)
                        position['profit_lock_armed'] = armed
                        position['profit_lock_arm_usd'] = float(profit_cfg['profit_lock_arm_usd'])
                        position['profit_lock_trigger_usd'] = round(peak*profit_cfg['profit_lock_retained_fraction'], 2) if armed else None
                lane_status = ('POSITION OPEN' if positions else
                    decision['blocks'][0] if decision['blocks'] else
                    timing_blocks[0] if timing_blocks else 'ENTRY ELIGIBLE')
                lanes[name] = {"decision": decision, "positions": positions, "closed_trades": history,
                    "exit_policy": args.exit_policy, "adaptive_exit": exit_decision,
                    "adaptive_market": exit_context,
                    "conscience": exit_decision.get("conscience", {}),
                    "risk_unit_usd": _lane_risk_usd(cfg, positions, float(snapshot.contract_size)),
                    "entry_mode": str(cfg.get("entry_mode", "CONSENSUS_2_OF_3")),
                    "exit_frame": str(cfg.get("exit_frame", "")),
                    "micro_flow": flow_read,
                    "entries_last_hour": len([t for t in lane_state.get("entry_times", [])
                                              if time.time() - t <= 3600.0]),
                    "execution_history_available": lane_state.get('history_available', True),
                    "consecutive_losses": int(lane_state.get("consecutive_losses", 0)),
                    "confirmation_cycles": lane_state["cycles"], "confirmation_required": cfg["confirmation_cycles"],
                    "signal_age_seconds": round(signal_age, 1),
                    "signal_age_required_seconds": float(cfg.get("minimum_signal_seconds", 0.0)),
                    "entry_timing_ready": timing_ready, "entry_timing_blocks": timing_blocks,
                    "max_positions": (min(cfg["max_positions"], inverse_settings.MAX_INVERSE_POSITIONS)
                                      if inverse_settings.PAIRING_ENABLED else cfg["max_positions"])
                                      if name == 'SCALP' else 0, "lot_size": settings.LOT_SIZE,
                    "cumulative_take_profit_usd": settings.HORIZON_CUMULATIVE_TAKE_PROFIT_USD if args.exit_policy == 'legacy' else None,
                    "stop_mode": cfg["stop_mode"],
                    "cumulative_stop_loss_usd": cfg.get("cumulative_stop_loss_usd"),
                    "individual_stop_loss_usd": cfg.get("individual_stop_loss_usd"),
                    "floating_profit": lane_profit,
                    "history_limit": settings.HORIZON_HISTORY_LIMIT, "history_reset_at": resets.get(name, ""),
                    "last_execution": lane_state["last_execution"],
                    "status": lane_status}
            phase_started = _mark_phase(phase_timings, 'lanes', phase_started)
            if refresh_history:
                last_history_fetch = time.monotonic()
            if recorder is not None:
                recorder.record(snapshot,lanes,macro)
            if exit_store is not None:
                exit_store.save(state,time.time())
            if paper is not None:
                paper.save()
                pnl = paper.pnl(pnl_started.timestamp())
            phase_started = _mark_phase(phase_timings, 'persistence', phase_started)
            updated = datetime.now(timezone.utc)
            all_positions = [dict(p, horizon=name) for name, lane in lanes.items() for p in lane["positions"]]
            status_payload = {"status": "RUNNING", "status_message": health['reason'],
                "updated_at": updated.isoformat(), "updated_local": updated.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
                "mode": args.mode, "cycle": cycle, "lanes": lanes, "positions": all_positions, "pnl": pnl,
                "account_fingerprint": bound_account_fingerprint,
                "paper_trading": paper is not None, "learned_policy_mode": args.learned_policy,
                "source_intelligence": source_intelligence,
                "market_health": health, "advisor_errors": dict(advisor_errors),
                "advisor_source_health": consensus.get('sources',{}),
                "advisor_provenance": {
                    "MT5_CANDLES": {"provider": "Connected MT5 broker", "feature_family": "CANDLE_TREND"},
                    "API_CANDLES": {"provider": api_for_consensus.get('data_source','Unavailable API provider'),
                                    "feature_family": "CANDLE_TREND"},
                    "MT5_TICK_FLOW": {"provider": "Connected MT5 broker", "feature_family": "TICK_FLOW"},
                    "note": "Different feeds using the same candle model are consistency checks; statistical independence is unproven."},
                "tick_history_health": tick_report.get('history_health',{}),
                "loop_elapsed_ms": round((time.monotonic()-cycle_started)*1000,2),
                "history_refresh_ms": round(history_refresh_ms, 2),
                "phase_timings_ms": phase_timings,
                "previous_status_write_ms": round(previous_status_write_ms, 3),
                "candle_signal_cache": dict(hits=candle_signal.hits, misses=candle_signal.misses),
                "exit_context_cache": dict(hits=context_cache.hits, misses=context_cache.misses),
                "loss_baseline_at": pnl_started.astimezone(timezone.utc).isoformat(),
                "news_risk": news_risk, "macro_context": macro, "free_macro_context": free_macro,
                "economic_advisor_v5": economic, "calendar_status": calendar_status,
                "main_official_calendar": main_calendar,
                "official_release_monitor": official, "background_refresh_errors": dict(background.errors),
                "adaptive_state_recovery": exit_store.status if exit_store is not None else 'NOT_USED',
                "market": {"symbol": settings.SYMBOL, "bid": float(snapshot.bid), "ask": float(snapshot.ask),
                    "spread": float(snapshot.spread), "session": str(snapshot.session),
                    "broker_tick_age_seconds": health['quote_age_seconds'],
                    "api_bar_age_seconds": consensus.get('sources',{}).get('API_CANDLES',{}).get('bar_age_seconds'),
                    "v3_tick_count": tick_report.get("tick_count"), "v3_tick_age_seconds": tick_report.get("latest_tick_age_seconds")},
                "config": {"lot_size": settings.LOT_SIZE, "history_limit": settings.HORIZON_HISTORY_LIMIT,
                    "inverse_companion_supported": True,
                    "inverse_pairing_enabled": inverse_settings.PAIRING_ENABLED,
                    "max_positions_total": min(3, int(settings.MAX_POSITION_SLOTS)),
                    "starting_capital_usd": settings.STARTING_CAPITAL_USD,
                    "max_trade_risk_usd": settings.MAX_TRADE_RISK_USD,
                    "fast_micro_confirmation_required": settings.FAST_MICRO_CONFIRMATION_REQUIRED,
                    "max_positions_per_horizon": max(int(lane['max_positions']) for lane in settings.HORIZON_LANES.values()),
                    "trading_horizons": ["SCALP"],
                    "research_entry_hold": Path('data/runtime/gold_entry_research_hold.flag').exists(),
                    "broker_utc_offset_seconds": settings.MT5_SERVER_UTC_OFFSET_SECONDS,
                    "exit_policy": args.exit_policy,
                    "smc_policy": args.smc_policy,
                    "max_session_loss_usd": settings.MAX_SESSION_LOSS_USD if settings.SESSION_LOSS_STOP_ENABLED else None,
                    "session_loss_stop_enabled": settings.SESSION_LOSS_STOP_ENABLED,
                    "post_exit_analysis_seconds": settings.POST_EXIT_ANALYSIS_SECONDS,
                    "entry_coordination_mode": settings.ENTRY_COORDINATION_MODE,
                    "demo_only": True}}
            status_write_started = time.perf_counter()
            atomic_write_json("data/runtime/gold_consensus_status.json", status_payload, indent=2)
            previous_status_write_ms = (time.perf_counter()-status_write_started)*1000
            if time.monotonic() - last_display >= float(settings.DISPLAY_INTERVAL_SECONDS):
                _print_cycle(cycle, lanes, pnl, args.mode)
                last_display = time.monotonic()
            if stopped or loss_stop:
                print("Session stopped by a safety circuit breaker.")
                break
            time.sleep(max(0.0, settings.LOOP_INTERVAL_SECONDS - (time.monotonic() - cycle_started)))
        return 0
    except KeyboardInterrupt:
        print("Bot stopped with CTRL+C.")
        return 0
    except Exception as error:
        status_payload['last_error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        if background is not None:
            background.close()
        if source_background is not None:
            source_background.close()
        if paper is not None:
            for name in settings.HORIZON_LANES:
                paper.close_lane(name, 'Paper session shutdown with fresh sampled quote', now=time.time())
                if name in status_payload.get('lanes', {}):
                    lane = status_payload['lanes'][name]
                    lane['positions'] = paper.details(name)
                    lane['floating_profit'] = dict(available=True, profit=paper.floating(name), position_count=len(lane['positions']))
                    lane['closed_trades'] = list(reversed([t for t in paper.trades if t['horizon'] == name][-settings.HORIZON_HISTORY_LIMIT:]))
            paper.save()
            status_payload['pnl'] = paper.pnl()
            status_payload['positions'] = [dict(p) for p in paper.positions]
            status_payload['paper_account_path'] = str(paper.root/'account.json')
        if demo_armed and settings.CLOSE_POSITIONS_ON_STOP:
            try:
                import MetaTrader5 as mt5
                result = close_all_consensus_positions(mt5)
                print(f"Shutdown protection: closed {result['closed_count']} controlled position(s).")
            except Exception as error:
                print(f"Shutdown close error: {error}")
        if dashboard_server is not None:
            dashboard_server.shutdown(); dashboard_server.server_close()
        if dashboard_support is not None:
            dashboard_support.stop()
        if dashboard_thread is not None:
            dashboard_thread.join(timeout=5)
        stopped_at = datetime.now(timezone.utc)
        status_payload.update({"status": "STOPPED", "status_message": "The bot is not running.", "updated_at": stopped_at.isoformat(), "updated_local": stopped_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")})
        try:
            atomic_write_json("data/runtime/gold_consensus_status.json", status_payload, indent=2)
        except Exception:
            pass
        disarm_demo_session(); disconnect_mt5(); lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
