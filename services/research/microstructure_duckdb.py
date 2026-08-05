from __future__ import annotations

import glob
import os
from typing import Any

from config import scalping_settings


def _parquet_glob(root: str) -> str:
    return os.path.abspath(os.path.join(root, "**", "*.parquet")).replace("\\", "/")


def _has_files(root: str) -> bool:
    return bool(glob.glob(os.path.join(os.path.abspath(root), "**", "*.parquet"), recursive=True))


def build_microstructure_duckdb_catalog() -> dict[str, Any]:
    """Create read-only analytical views over the partitioned Parquet datasets."""
    try:
        import duckdb
    except ImportError as error:
        return {
            "success": False,
            "database": os.path.abspath(scalping_settings.SCALPING_DUCKDB_PATH),
            "views": [],
            "errors": [f"duckdb is not installed: {error}"],
        }

    database = os.path.abspath(scalping_settings.SCALPING_DUCKDB_PATH)
    os.makedirs(os.path.dirname(database), exist_ok=True)
    datasets = {
        "v_scalping_ticks": scalping_settings.SCALPING_TICK_DATA_ROOT,
        "v_microstructure_features": scalping_settings.SCALPING_MICROSTRUCTURE_FEATURE_ROOT,
        "v_execution_audit": scalping_settings.SCALPING_EXECUTION_AUDIT_PARQUET_ROOT,
    }
    views: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    connection = duckdb.connect(database)
    try:
        for view, root in datasets.items():
            if not _has_files(root):
                skipped.append(f"{view}: no Parquet files under {os.path.abspath(root)}")
                continue
            parquet = _parquet_glob(root).replace("'", "''")
            try:
                connection.execute(
                    f"CREATE OR REPLACE VIEW {view} AS "
                    f"SELECT * FROM read_parquet('{parquet}', "
                    "hive_partitioning=true, union_by_name=true)"
                )
                views.append(view)
            except Exception as error:
                errors.append(f"{view}: {type(error).__name__}: {error}")

        if "v_scalping_ticks" in views:
            connection.execute(
                """
                CREATE OR REPLACE VIEW v_scalping_ticks_deduplicated AS
                SELECT * EXCLUDE (duplicate_rank)
                FROM (
                    SELECT *,
                           row_number() OVER (
                               PARTITION BY tick_key
                               ORDER BY recorded_at_utc DESC
                           ) AS duplicate_rank
                    FROM v_scalping_ticks
                )
                WHERE duplicate_rank = 1
                """
            )
            views.append("v_scalping_ticks_deduplicated")

        if "v_execution_audit" in views:
            connection.execute(
                """
                CREATE OR REPLACE VIEW v_trade_lifecycle_summary AS
                SELECT
                    trade_id,
                    any_value(strategy_id) AS strategy_id,
                    any_value(symbol) AS symbol,
                    any_value(direction) AS direction,
                    max(CASE WHEN event_type = 'ENTRY' THEN audit_timestamp_utc END) AS entry_audit_time,
                    max(CASE WHEN event_type = 'EXIT' THEN audit_timestamp_utc END) AS exit_audit_time,
                    max(CASE WHEN event_type = 'ENTRY' THEN entry_slippage_usd END) AS entry_slippage_usd,
                    max(CASE WHEN event_type = 'EXIT' THEN exit_slippage_usd END) AS exit_slippage_usd,
                    max(maximum_favorable_excursion_usd) AS mfe_usd,
                    max(maximum_adverse_excursion_usd) AS mae_usd,
                    max(hold_seconds) AS hold_seconds,
                    max(realized_profit_usd) AS realized_profit_usd,
                    max(exit_reason) AS exit_reason
                FROM v_execution_audit
                GROUP BY trade_id
                """
            )
            views.append("v_trade_lifecycle_summary")
    finally:
        connection.close()

    return {
        "success": not errors,
        "database": database,
        "views": views,
        "skipped": skipped,
        "errors": errors,
    }


def query_microstructure_overview() -> dict[str, Any]:
    catalog = build_microstructure_duckdb_catalog()
    if not catalog.get("success"):
        return catalog
    try:
        import duckdb
    except ImportError:
        return catalog

    connection = duckdb.connect(catalog["database"], read_only=True)
    result: dict[str, Any] = dict(catalog)
    try:
        if "v_scalping_ticks" in catalog["views"]:
            result["raw_tick_rows"] = connection.execute(
                "SELECT count(*) FROM v_scalping_ticks"
            ).fetchone()[0]
        if "v_scalping_ticks_deduplicated" in catalog["views"]:
            result["tick_rows"] = connection.execute(
                "SELECT count(*) FROM v_scalping_ticks_deduplicated"
            ).fetchone()[0]
        if "v_microstructure_features" in catalog["views"]:
            result["feature_rows"] = connection.execute(
                "SELECT count(*) FROM v_microstructure_features"
            ).fetchone()[0]
            result["feature_direction_counts"] = connection.execute(
                "SELECT direction, count(*) AS rows FROM v_microstructure_features "
                "GROUP BY direction ORDER BY rows DESC"
            ).fetchall()
        if "v_execution_audit" in catalog["views"]:
            result["audit_rows"] = connection.execute(
                "SELECT count(*) FROM v_execution_audit"
            ).fetchone()[0]
            result["audit_event_counts"] = connection.execute(
                "SELECT event_type, count(*) AS rows FROM v_execution_audit "
                "GROUP BY event_type ORDER BY event_type"
            ).fetchall()
    finally:
        connection.close()
    return result
