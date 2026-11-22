"""Replay observed MT5 bid/ask ticks through a paper-only event loop."""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import statistics
import time

import numpy as np


@dataclass(frozen=True)
class Quote:
    time_msc: int
    bid: float
    ask: float


@dataclass(frozen=True)
class PaperTrade:
    side: str
    signal_time_msc: int
    entry_time_msc: int
    entry_price: float
    exit_time_msc: int
    exit_price: float
    gross_price_units: float
    estimated_net_price_units: float
    signal_move: float


@dataclass
class PendingEntry:
    side: int
    signal_time_msc: int
    due_time_msc: int
    signal_move: float


@dataclass
class OpenPaperPosition:
    side: int
    signal_time_msc: int
    entry_time_msc: int
    entry_price: float
    signal_move: float


def load_quotes(path: Path) -> list[Quote]:
    """Load the real-tick NPZ schema written by export_gold_tick_probe.py."""
    with np.load(path, allow_pickle=False) as data:
        required = {"utc_time_msc", "bid", "ask"}
        missing = required.difference(data.files)
        if missing:
            raise ValueError(f"Tick archive is missing arrays: {', '.join(sorted(missing))}")
        times = np.asarray(data["utc_time_msc"])
        bids = np.asarray(data["bid"])
        asks = np.asarray(data["ask"])

    if times.ndim != 1 or bids.ndim != 1 or asks.ndim != 1:
        raise ValueError("Tick arrays must be one-dimensional.")
    if not (len(times) == len(bids) == len(asks)) or len(times) < 2:
        raise ValueError("Tick arrays must have matching lengths and at least two quotes.")
    if not np.issubdtype(times.dtype, np.number):
        raise ValueError("Tick timestamps must be numeric UTC milliseconds.")
    if not np.isfinite(times).all() or not np.isfinite(bids).all() or not np.isfinite(asks).all():
        raise ValueError("Tick arrays contain non-finite values.")
    if np.any(times <= 0) or np.any(times != np.floor(times)):
        raise ValueError("Tick timestamps must be positive integer milliseconds.")
    if np.any(np.diff(times) <= 0):
        raise ValueError("Tick timestamps must be strictly increasing; sort/deduplicate the source data.")
    if np.any(bids <= 0) or np.any(asks < bids):
        raise ValueError("Ticks contain invalid bid/ask prices.")
    return [
        Quote(int(stamp), float(bid), float(ask))
        for stamp, bid, ask in zip(times, bids, asks)
    ]


def replay(
    quotes: list[Quote],
    *,
    lookback_ms: int = 250,
    entry_threshold: float = 0.05,
    max_spread: float = 0.60,
    latency_ms: int = 10,
    holding_ms: int = 500,
    max_quote_gap_ms: int = 2_000,
    reentry_cooldown_ms: int = 500,
    max_entries_per_hour: int = 60,
    round_trip_cost_price: float = 0.0,
    slippage_per_side_price: float = 0.0,
) -> dict:
    if len(quotes) < 2:
        raise ValueError("At least two quotes are required.")
    if min(lookback_ms, latency_ms, holding_ms, max_quote_gap_ms, reentry_cooldown_ms) < 0:
        raise ValueError("Timing parameters cannot be negative.")
    if lookback_ms == 0 or holding_ms == 0 or max_quote_gap_ms == 0:
        raise ValueError("Lookback, holding, and maximum quote-gap values must be positive.")
    if (not math.isfinite(entry_threshold) or not math.isfinite(max_spread)
            or entry_threshold <= 0 or max_spread <= 0):
        raise ValueError("Entry threshold and maximum spread must be positive.")
    if max_entries_per_hour <= 0:
        raise ValueError("Maximum entries per hour must be positive.")
    if (not math.isfinite(round_trip_cost_price) or round_trip_cost_price < 0
            or not math.isfinite(slippage_per_side_price) or slippage_per_side_price < 0):
        raise ValueError("Cost and slippage assumptions must be finite and non-negative.")
    for quote in quotes:
        if (quote.time_msc <= 0 or not math.isfinite(quote.bid) or not math.isfinite(quote.ask)
                or quote.bid <= 0 or quote.ask < quote.bid):
            raise ValueError("Quotes contain invalid timestamps or bid/ask prices.")
    for previous, current in zip(quotes, quotes[1:]):
        if current.time_msc <= previous.time_msc:
            raise ValueError("Quotes must be strictly chronological.")

    lookback: deque[Quote] = deque()
    pending: PendingEntry | None = None
    position: OpenPaperPosition | None = None
    trades: list[PaperTrade] = []
    entry_times: deque[int] = deque()
    gaps = 0
    stale_entry_cancellations = 0
    spread_rejections = 0
    hourly_cap_rejections = 0
    handler_times_ns: list[int] = []
    previous_time = quotes[0].time_msc
    last_trade_time = -10**30
    unresolved_position_after_gap = False

    for quote in quotes:
        started = time.perf_counter_ns()
        spread = quote.ask - quote.bid
        spread_valid = spread <= max_spread
        if not spread_valid:
            spread_rejections += 1
            lookback.clear()
        gap = quote.time_msc - previous_time
        if gap > max_quote_gap_ms:
            gaps += 1
            lookback.clear()
            if position is not None:
                unresolved_position_after_gap = True
            if pending is not None:
                pending = None
                stale_entry_cancellations += 1

        while entry_times and quote.time_msc - entry_times[0] >= 3_600_000:
            entry_times.popleft()
        if pending is not None:
            age = quote.time_msc - pending.signal_time_msc
            if not spread_valid:
                pending = None
            elif age > max_quote_gap_ms:
                pending = None
                stale_entry_cancellations += 1
            elif quote.time_msc >= pending.due_time_msc:
                if len(entry_times) >= max_entries_per_hour:
                    hourly_cap_rejections += 1
                else:
                    side = pending.side
                    entry_price = quote.ask if side > 0 else quote.bid
                    entry_price += side * slippage_per_side_price
                    position = OpenPaperPosition(
                        side=side,
                        signal_time_msc=pending.signal_time_msc,
                        entry_time_msc=quote.time_msc,
                        entry_price=entry_price,
                        signal_move=pending.signal_move,
                    )
                    entry_times.append(quote.time_msc)
                pending = None

        if (position is not None and not unresolved_position_after_gap
                and quote.time_msc - position.entry_time_msc >= holding_ms):
            exit_price = quote.bid if position.side > 0 else quote.ask
            exit_price -= position.side * slippage_per_side_price
            gross_price_units = position.side * (exit_price - position.entry_price)
            trades.append(PaperTrade(
                side="BUY" if position.side > 0 else "SELL",
                signal_time_msc=position.signal_time_msc,
                entry_time_msc=position.entry_time_msc,
                entry_price=position.entry_price,
                exit_time_msc=quote.time_msc,
                exit_price=exit_price,
                gross_price_units=gross_price_units,
                estimated_net_price_units=gross_price_units - round_trip_cost_price,
                signal_move=position.signal_move,
            ))
            position = None
            last_trade_time = quote.time_msc

        if (position is None and pending is None and not unresolved_position_after_gap
                and spread_valid):
            cutoff = quote.time_msc - lookback_ms
            lookback.append(quote)
            while len(lookback) > 1 and lookback[1].time_msc <= cutoff:
                lookback.popleft()
            reference = lookback[0]
            reference_age = quote.time_msc - reference.time_msc
            if (reference_age >= lookback_ms
                    and reference_age <= lookback_ms + max_quote_gap_ms
                    and quote.time_msc - last_trade_time >= reentry_cooldown_ms):
                move = (quote.bid + quote.ask - reference.bid - reference.ask) / 2.0
                if abs(move) >= entry_threshold:
                    if len(entry_times) >= max_entries_per_hour:
                        hourly_cap_rejections += 1
                    else:
                        pending = PendingEntry(
                            side=1 if move > 0 else -1,
                            signal_time_msc=quote.time_msc,
                            due_time_msc=quote.time_msc + latency_ms,
                            signal_move=move,
                        )

        # Keep the lookback warm even while a simulated position is open.
        if spread_valid and (not lookback or lookback[-1].time_msc != quote.time_msc):
            lookback.append(quote)
            cutoff = quote.time_msc - lookback_ms
            while len(lookback) > 1 and lookback[1].time_msc <= cutoff:
                lookback.popleft()

        previous_time = quote.time_msc
        handler_times_ns.append(time.perf_counter_ns() - started)

    intervals = [b.time_msc - a.time_msc for a, b in zip(quotes, quotes[1:])]
    gross = [trade.gross_price_units for trade in trades]
    net = [trade.estimated_net_price_units for trade in trades]
    return {
        "mode": "PAPER_REPLAY_ONLY",
        "quotes": len(quotes),
        "start_time_msc": quotes[0].time_msc,
        "end_time_msc": quotes[-1].time_msc,
        "median_quote_interval_ms": statistics.median(intervals),
        "p95_quote_interval_ms": float(np.percentile(intervals, 95)),
        "maximum_quote_gap_ms": max(intervals),
        "gaps_over_limit": gaps,
        "spread_rejections": spread_rejections,
        "stale_entry_cancellations": stale_entry_cancellations,
        "hourly_cap_rejections": hourly_cap_rejections,
        "unresolved_position_after_data_gap": unresolved_position_after_gap,
        "paper_trades_closed": len(trades),
        "open_paper_position": ({
            **asdict(position),
            "unrealized_gross_price_units_after_crossing_spread": position.side * (
                (quotes[-1].bid if position.side > 0 else quotes[-1].ask) - position.entry_price
            ),
        } if position else None),
        "pending_paper_entry": asdict(pending) if pending else None,
        "gross_price_units_after_crossing_spread": {
            "sum": sum(gross),
            "mean": statistics.mean(gross) if gross else None,
            "positive_trade_fraction": sum(value > 0 for value in gross) / len(gross) if gross else None,
        },
        "estimated_net_price_units_after_assumed_costs": {
            "sum": sum(net),
            "mean": statistics.mean(net) if net else None,
            "positive_trade_fraction": sum(value > 0 for value in net) / len(net) if net else None,
        },
        "local_replay_handler_time_ns": {
            "median": statistics.median(handler_times_ns),
            "p95": float(np.percentile(handler_times_ns, 95)),
            "maximum": max(handler_times_ns),
            "note": "Local replay processing only; not live signal, network, broker, venue, or fill latency.",
        },
        "parameters": {
            "lookback_ms": lookback_ms,
            "entry_threshold_price": entry_threshold,
            "max_spread_price": max_spread,
            "assumed_submission_latency_ms": latency_ms,
            "holding_ms": holding_ms,
            "max_quote_gap_ms": max_quote_gap_ms,
            "reentry_cooldown_ms": reentry_cooldown_ms,
            "max_entries_per_hour": max_entries_per_hour,
            "round_trip_cost_price_units": round_trip_cost_price,
            "slippage_per_side_price_units": slippage_per_side_price,
        },
        "limitations": [
            "Uses observed MT5 top-of-book bid/ask quotes only; not exchange depth or a centralized gold order book.",
            "Paper fills use the first observed quote at or after assumed submission latency; queue position, partial fills, rejects, and market impact are not modeled.",
            "Bid/ask crossing is reflected in price results; user-supplied cost/slippage assumptions are not verified broker charges.",
            "Price-unit results are not account-currency P&L or evidence of profitability.",
            "A replay and local handler timing do not make this HFT or measure end-to-end live latency.",
        ],
        "trades": [asdict(trade) for trade in trades],
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay an observed MT5 tick-probe NPZ through a paper-only event loop."
    )
    parser.add_argument("--ticks", required=True, type=Path, help="NPZ with utc_time_msc, bid, and ask arrays.")
    parser.add_argument("--lookback-ms", type=int, default=250)
    parser.add_argument("--entry-threshold-price", type=float, default=0.05)
    parser.add_argument("--max-spread-price", type=float, default=0.60)
    parser.add_argument("--assumed-latency-ms", type=int, default=10)
    parser.add_argument("--holding-ms", type=int, default=500)
    parser.add_argument("--max-quote-gap-ms", type=int, default=2_000)
    parser.add_argument("--reentry-cooldown-ms", type=int, default=500)
    parser.add_argument("--max-entries-per-hour", type=int, default=60)
    parser.add_argument("--round-trip-cost-price", type=float, default=0.0)
    parser.add_argument("--slippage-per-side-price", type=float, default=0.0)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    report = replay(
        load_quotes(args.ticks),
        lookback_ms=args.lookback_ms,
        entry_threshold=args.entry_threshold_price,
        max_spread=args.max_spread_price,
        latency_ms=args.assumed_latency_ms,
        holding_ms=args.holding_ms,
        max_quote_gap_ms=args.max_quote_gap_ms,
        reentry_cooldown_ms=args.reentry_cooldown_ms,
        max_entries_per_hour=args.max_entries_per_hour,
        round_trip_cost_price=args.round_trip_cost_price,
        slippage_per_side_price=args.slippage_per_side_price,
    )
    report["source"] = str(args.ticks)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
