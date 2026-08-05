from __future__ import annotations

from datetime import datetime
from typing import Any

from config import scalping_settings
from models.scalping_state import ScalpSignalState, ScalpingSnapshotState
from services.execution.scalp_demo_journal import (
    load_cumulative_demo_history as load_all_demo_history,
)
from services.research.v6_approval import revoke_v6_approval
from services.risk.demo_loss_session import (
    DATETIME_FORMAT,
    latch_demo_loss_stop,
    load_demo_loss_session,
    prepare_demo_loss_session,
    touch_demo_loss_session,
)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_direction(value: Any) -> str:
    text = str(value or "NEUTRAL").strip().upper()
    if text in {"BUY", "BULL", "BULLISH", "LONG"}:
        return "BUY"
    if text in {"SELL", "BEAR", "BEARISH", "SHORT"}:
        return "SELL"
    return "NEUTRAL"


def _score_metrics(signal: ScalpSignalState) -> tuple[float, float]:
    metrics = _dict(getattr(signal, "metrics", {}))
    diagnostics = _dict(metrics.get("score_diagnostics"))
    direct = _dict(diagnostics.get("direct_score_decision"))
    winner = _float(direct.get("winner_score", getattr(signal, "score", 0.0)))
    margin = _float(direct.get("margin", diagnostics.get("direction_margin", 0.0)))
    return winner, margin


def _micro_metrics(signal: ScalpSignalState) -> tuple[str, float]:
    metrics = _dict(getattr(signal, "metrics", {}))
    micro = _dict(metrics.get("microstructure"))
    return _normalize_direction(micro.get("direction")), _float(micro.get("confidence"))


def _parse(value: Any) -> datetime | None:
    text = str(value or "").strip()
    for pattern in (DATETIME_FORMAT, "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(text[:26], pattern)
        except (TypeError, ValueError):
            continue
    return None


def _records_since(rows: list[dict[str, Any]], started_at: datetime) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for item in rows:
        stamp = _parse(item.get("closed_at") or item.get("opened_at") or item.get("recorded_at"))
        if stamp is not None and stamp >= started_at:
            selected.append(item)
    return selected


def _closed_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item for item in rows
        if str(item.get("status", "")).upper() == "CLOSED"
        and item.get("final_profit_usd") is not None
    ]


def _trailing_losses(closed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(closed, key=lambda row: str(row.get("closed_at", "")))
    result: list[dict[str, Any]] = []
    for item in reversed(ordered):
        if _float(item.get("final_profit_usd")) < 0:
            result.append(item)
        else:
            break
    result.reverse()
    return result


def _cooldown(closed: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    threshold = int(scalping_settings.SCALPING_DEMO_LOSS_STREAK_COOLDOWN_AFTER_LOSSES)
    duration = float(scalping_settings.SCALPING_DEMO_LOSS_STREAK_COOLDOWN_SECONDS)
    losses = _trailing_losses(closed)
    groups = len(losses) // max(1, threshold)
    state = {
        "active": False,
        "remaining_seconds": 0.0,
        "duration_seconds": duration,
        "consecutive_losses": len(losses),
        "completed_groups": groups,
    }
    if groups <= 0:
        return state
    trigger = losses[groups * threshold - 1]
    triggered_at = _parse(trigger.get("closed_at"))
    if triggered_at is None:
        return state
    remaining = max(0.0, duration - max(0.0, (now - triggered_at).total_seconds()))
    state.update(
        {
            "active": remaining > 0.0,
            "remaining_seconds": round(remaining, 3),
            "triggered_at": triggered_at.strftime(DATETIME_FORMAT),
        }
    )
    return state


def evaluate_scalping_demo_risk(
    snapshot: ScalpingSnapshotState,
    signal: ScalpSignalState,
    news_risk: dict[str, Any],
    *,
    account_info: Any | None = None,
    open_floating_profit_usd: float = 0.0,
) -> dict[str, Any]:
    now = datetime.now()
    prepared = prepare_demo_loss_session(account_info, reset=False)
    state = dict(prepared.get("state") or load_demo_loss_session())
    started_at = _parse(state.get("started_at")) or now
    session_rows = _records_since(load_all_demo_history(), started_at)
    closed = _closed_records(session_rows)
    realized = round(sum(_float(item.get("final_profit_usd")) for item in closed), 2)
    floating = round(float(open_floating_profit_usd or 0.0), 2)
    cumulative = round(realized + floating, 2)
    cooldown = _cooldown(closed, now)
    limit = float(scalping_settings.SCALPING_DEMO_CUMULATIVE_LOSS_LIMIT_USD)
    stop_latched = bool(state.get("stop_latched", False))
    cumulative_loss_stop_reached = cumulative <= -limit
    if cumulative_loss_stop_reached and not stop_latched:
        state = latch_demo_loss_stop(cumulative)
        stop_latched = True
    else:
        touch_demo_loss_session(
            session_realized_profit_usd=realized,
            session_floating_profit_usd=floating,
            session_total_profit_usd=cumulative,
            closed_trade_count=len(closed),
        )

    reasons: list[str] = []
    if not prepared.get("allowed", False):
        reasons.append(str(prepared.get("reason") or "Cumulative loss session is unavailable."))
    if not signal.allowed:
        reasons.append("No confirmed demo scalp entry signal.")
    quote_age_seconds = float(getattr(snapshot, "quote_age_seconds", 0.0) or 0.0)
    max_quote_age_seconds = float(scalping_settings.SCALPING_V6_MAX_QUOTE_AGE_SECONDS)
    if quote_age_seconds > max_quote_age_seconds:
        reasons.append(
            f"MT5 quote is stale: no new quote for {quote_age_seconds:.1f}s "
            f"> {max_quote_age_seconds:.1f}s."
        )
    metrics = _dict(getattr(signal, "metrics", {}))
    v6_gate = _dict(metrics.get("v6_candidate_gate"))
    spread_policy = {
        "accepted": bool(v6_gate.get("allowed", False)),
        "mode": "V6_STRICT_RESEARCH_GATE",
        "spread_usd": _float(v6_gate.get("spread_usd"), float(snapshot.spread)),
        "spread_atr_ratio": _float(v6_gate.get("spread_atr")),
        "maximum_spread_usd": float(scalping_settings.SCALPING_V6_MAX_SPREAD_USD),
        "failed_checks": list(v6_gate.get("failed_checks", []) or []),
        "reason": str(v6_gate.get("reason", "V6 candidate gate is unavailable.")),
    }
    if not bool(v6_gate.get("allowed", False)):
        reasons.append(spread_policy["reason"])
    if not bool(news_risk.get("allowed", False)):
        reasons.extend(news_risk.get("block_reasons", []) or ["News filter blocked entry."])
    if stop_latched or cumulative_loss_stop_reached:
        reasons.append(
            f"Cumulative demo loss stop reached/latched: ${cumulative:.2f} <= -${limit:.2f}. "
            "Manual --reset-loss-session is required before another demo session."
        )
    if bool(cooldown.get("active", False)):
        threshold = int(scalping_settings.SCALPING_DEMO_LOSS_STREAK_COOLDOWN_AFTER_LOSSES)
        reasons.append(
            f"Demo {threshold}-loss cooldown active: "
            f"{cooldown['remaining_seconds']:.1f}s remaining."
        )
        if bool(getattr(scalping_settings, "SCALPING_V6_DEMO_RETURN_TO_SHADOW_AFTER_LOSSES", False)):
            try:
                revoke_v6_approval(f"Automatic revocation after {threshold} consecutive approved-demo losses.")
            except Exception:
                pass
            reasons.append("V6 approval revoked after the loss circuit breaker; return to shadow calibration.")

    # V6.2 deliberately has no hidden post-loss entry policy. The exact shadow
    # hypothesis remains unchanged in approved demo. Three consecutive losses
    # revoke approval and force a fresh shadow/walk-forward review.
    consecutive_losses = int(cooldown.get("consecutive_losses", 0))
    recovery_mode = False
    recovery_checks: dict[str, bool] = {}
    return_to_shadow_required = bool(
        consecutive_losses >= int(scalping_settings.SCALPING_V6_DEMO_MAX_CONSECUTIVE_LOSSES)
    )
    if return_to_shadow_required:
        try:
            revoke_v6_approval(
                f"Automatic revocation after {consecutive_losses} consecutive approved-demo losses."
            )
        except Exception:
            pass
        reason = "V6 approved-demo circuit breaker reached; approval revoked and shadow recalibration is required."
        if reason not in reasons:
            reasons.append(reason)

    session_stop_required = bool(stop_latched or cumulative_loss_stop_reached)
    trade_count = sum(
        1 for item in session_rows
        if str(item.get("record_type", "")).upper() in {"OPEN", "RECOVERED_POSITION"}
    )

    return {
        "allowed": not reasons,
        "spread_policy": spread_policy,
        "action": "SCALP_DEMO_RISK_ALLOWED" if not reasons else "SCALP_DEMO_RISK_BLOCKED",
        "trade_limit_enabled": False,
        "session_trade_count": trade_count,
        "session_closed_count": len(closed),
        "session_realized_profit": realized,
        "session_floating_profit": floating,
        "session_total_profit": cumulative,
        "cumulative_loss_limit_usd": limit,
        # Compatibility keys retained for existing printers/tests. They now mean
        # cumulative loss-session values and do not reset at midnight.
        "daily_trade_count": trade_count,
        "daily_closed_count": len(closed),
        "daily_realized_profit": realized,
        "maximum_drawdown": max(0.0, -cumulative),
        "consecutive_losses": consecutive_losses,
        "loss_cooldown_active": bool(cooldown.get("active", False)),
        "loss_cooldown_remaining_seconds": float(cooldown.get("remaining_seconds", 0.0)),
        "loss_cooldown_duration_seconds": float(cooldown.get("duration_seconds", 0.0)),
        "loss_recovery_mode": recovery_mode,
        "loss_recovery_checks": recovery_checks,
        "cumulative_loss_stop_reached": bool(cumulative_loss_stop_reached),
        "daily_loss_stop_reached": bool(cumulative_loss_stop_reached),
        "drawdown_stop_reached": False,
        "stop_latched": bool(stop_latched),
        "loss_session_started_at": state.get("started_at"),
        "session_stop_required": session_stop_required,
        "return_to_shadow_required": return_to_shadow_required,
        "quote_age_seconds": quote_age_seconds,
        "max_quote_stale_seconds": max_quote_age_seconds,
        "block_reasons": reasons,
    }
