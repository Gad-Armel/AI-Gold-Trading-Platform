"""Validated, read-only transport for the manual scalp advisory dashboard card."""
from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
import time

REPORT = Path(__file__).resolve().parents[2] / "data/runtime/gold_manual_scalp_advisory.json"
MAX_REPORT_BYTES = 1_000_000
MAX_LIVE_AGE_SECONDS = 5.0


def _reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON number: {value}")


def _epoch(value: object) -> float:
    if not isinstance(value, str) or not value:
        raise ValueError("Missing advisory timestamp.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Advisory timestamps must include a timezone.")
    return parsed.timestamp()


def _number(value: object, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Invalid advisory number.")
    result = float(value)
    if minimum is not None and result < minimum:
        raise ValueError("Advisory number is below its valid range.")
    if maximum is not None and result > maximum:
        raise ValueError("Advisory number is above its valid range.")
    return result


def read_manual_scalp(path: Path = REPORT, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    result = {
        "state": "waiting",
        "message": "Waiting for the separate read-only manual scalp advisor.",
        "report": None,
        "age_seconds": None,
        "server_time": now,
    }
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_REPORT_BYTES + 1)
        if len(data) > MAX_REPORT_BYTES:
            raise ValueError("Manual scalp report exceeds the size limit.")
        report = json.loads(data.decode("utf-8-sig"), parse_constant=_reject_constant)
        if not isinstance(report, dict) or report.get("symbol") != "XAUUSD":
            raise ValueError("Expected a manual XAUUSD scalp report.")
        if report.get("execution_enabled") is not False or report.get("orders_sent") is not False:
            raise ValueError("Manual advisor report must explicitly disable execution.")
        if report.get("action") not in {"BUY", "SELL", "WAIT"} or report.get("bias") not in {"BUY", "SELL", "WAIT"}:
            raise ValueError("Invalid manual scalp decision.")
        generated = _epoch(report.get("generated_at"))
        valid_until = _epoch(report.get("valid_until"))
        if valid_until <= generated or valid_until - generated > 30:
            raise ValueError("Manual scalp validity window is invalid.")
        _number(report.get("directional_evidence_score"), minimum=0, maximum=100)
        quote = report.get("quote")
        if not isinstance(quote, dict):
            raise ValueError("Manual scalp quote is missing.")
        bid = _number(quote.get("bid"), minimum=0.000000001)
        ask = _number(quote.get("ask"), minimum=bid)
        spread = _number(quote.get("spread"), minimum=0)
        if abs(spread - (ask - bid)) > 0.00001:
            raise ValueError("Manual scalp spread does not match its quote.")
        reports = report.get("reports")
        if not isinstance(reports, dict):
            raise ValueError("Manual scalp model evidence is missing.")
        for action_key, score_key in (("candle_action", "candle_score"), ("tick_action", "tick_score")):
            if reports.get(action_key) not in {"BUY", "SELL", "WAIT"}:
                raise ValueError("Invalid manual scalp model direction.")
            _number(reports.get(score_key), minimum=0, maximum=100)
        for field in ("reasons", "blocks"):
            items = report.get(field)
            if not isinstance(items, list) or len(items) > 100 or any(not isinstance(item, str) for item in items):
                raise ValueError(f"Invalid manual scalp {field}.")
        if report["action"] in {"BUY", "SELL"}:
            if report["bias"] != report["action"] or reports["candle_action"] != report["action"] or reports["tick_action"] != report["action"] or report["blocks"]:
                raise ValueError("Actionable advisory lacks unblocked two-model agreement.")
            levels = report.get("scenario_levels")
            if not isinstance(levels, dict) or not isinstance(levels.get("entry_zone"), list) or len(levels["entry_zone"]) != 2:
                raise ValueError("Actionable advisory is missing scenario levels.")
            _number(levels["entry_reference"], minimum=0.000000001)
            _number(levels["sl"], minimum=0.000000001)
            for name in ("tp1", "tp2", "tp3"):
                _number(levels[name], minimum=0.000000001)
            _number(levels["entry_zone"][0], minimum=0.000000001)
            _number(levels["entry_zone"][1], minimum=levels["entry_zone"][0])
            if ask < bid:
                raise ValueError("Manual scalp quote is crossed.")
        age = now - generated
        expiry_age = now - valid_until
        result.update(report=report, age_seconds=round(max(age, 0), 2))
        if age < -5:
            result.update(state="stale", message="Manual scalp report is future-dated; check the system clock.")
        elif age > MAX_LIVE_AGE_SECONDS or expiry_age >= 0:
            result.update(state="stale", message="Manual scalp report is stale or expired; do not treat it as a current signal.")
        else:
            result.update(state="live", message="Fresh manual-only analysis. It is not a trade instruction or placed order.")
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError, json.JSONDecodeError) as error:
        result.update(state="error", message=f"Cannot read manual scalp report: {error}")
    return result
