from __future__ import annotations

"""Validate and store point-in-time slow gold-demand observations.

Use published WGC/IMF central-bank and ETF tonnage plus the official CFTC Gold
managed-money change. This tool deliberately requires the user to name the
source and observation date; an undocumented number cannot influence V5.
"""

import argparse
import math
from datetime import datetime, timezone
from typing import Any

from services.utils.atomic_json import atomic_write_json


def build_context(args: argparse.Namespace) -> dict[str, Any]:
    try:
        observed = datetime.fromisoformat(str(args.observed_at).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("--observed-at must be an ISO-8601 timestamp or date.") from error
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    observed = observed.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if observed > now:
        raise ValueError("--observed-at cannot be in the future.")
    values = {
        "central_bank_net_tonnes_change": args.central_bank_net_tonnes,
        "etf_tonnes_change": args.etf_net_tonnes,
        "managed_money_net_change_4w": args.managed_money_net_change_4w,
        "managed_money_percentile_52w": args.managed_money_percentile_52w,
    }
    if all(value is None for value in values.values()):
        raise ValueError("Provide at least one institutional observation.")
    for name, value in values.items():
        if value is not None and not math.isfinite(float(value)):
            raise ValueError(f"{name} must be finite.")
    if args.managed_money_percentile_52w is not None and not 0 <= args.managed_money_percentile_52w <= 1:
        raise ValueError("--managed-money-percentile-52w must be between 0 and 1.")
    age_days = max(0.0, (now - observed).total_seconds() / 86400.0)
    common = {
        "available": True,
        "observed_at": observed.isoformat(),
        "published_at": now.isoformat(),
        "source": str(args.source).strip(),
        "source_quality": 0.75,
        "revision_risk": "UNKNOWN",
    }
    observations: dict[str, dict[str, Any]] = {}
    if args.central_bank_net_tonnes is not None:
        observations["central_bank"] = {
            **common, "metric": "NET_PURCHASES_TONNES", "period": "UNSPECIFIED",
            "net_tonnes": args.central_bank_net_tonnes,
        }
    if args.etf_net_tonnes is not None:
        observations["gold_etf"] = {
            **common, "metric": "GOLD_ETF_NET_FLOW_TONNES", "period": "UNSPECIFIED",
            "net_tonnes": args.etf_net_tonnes,
        }
    if args.managed_money_net_change_4w is not None or args.managed_money_percentile_52w is not None:
        observations["managed_money"] = {
            **common, "metric": "COMEX_GOLD_MANAGED_MONEY", "period": "WEEKLY",
            **({"managed_money_net_change_4w": args.managed_money_net_change_4w}
               if args.managed_money_net_change_4w is not None else {}),
            **({"managed_money_percentile_52w": args.managed_money_percentile_52w}
               if args.managed_money_percentile_52w is not None else {}),
        }
    return {
        "schema_version": 2,
        "observed_at": observed.isoformat(),
        "recorded_at": now.isoformat(),
        "generated_at": now.isoformat(),
        "last_attempt_at": now.isoformat(),
        "last_success_at": now.isoformat(),
        "refresh_status": "MANUAL_VERIFIED",
        "refresh_errors": {},
        "observations": observations,
        "age_days": round(age_days, 4),
        "source": str(args.source).strip(),
        **{key: value for key, value in values.items() if value is not None},
        "usage": "SWING_CONTEXT_ONLY",
        "warning": "Delayed/revisable observations; never a standalone entry signal.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Store verified slow gold institutional context for Economic Advisor V5.")
    parser.add_argument("--source", required=True, help="Exact publication/source name or URL.")
    parser.add_argument("--observed-at", required=True, help="ISO date/timestamp represented by the values.")
    parser.add_argument("--central-bank-net-tonnes", type=float)
    parser.add_argument("--etf-net-tonnes", type=float)
    parser.add_argument("--managed-money-net-change-4w", type=float)
    parser.add_argument("--managed-money-percentile-52w", type=float)
    parser.add_argument("--output", default="data/context/gold_institutional_context.json")
    args = parser.parse_args()
    if not str(args.source).strip():
        parser.error("--source cannot be blank.")
    try:
        payload = build_context(args)
    except ValueError as error:
        parser.error(str(error))
    atomic_write_json(args.output, payload, indent=2)
    print(f"Institutional context updated: {args.output}")
    print(f"Observed: {payload['observed_at']} | Source: {payload['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
