from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from config import scalping_settings
from services.microstructure.feature_engine import MicrostructureFeatureState
from services.microstructure.parquet_store import PartitionedParquetBuffer


_WRITER = PartitionedParquetBuffer(
    scalping_settings.SCALPING_MICROSTRUCTURE_FEATURE_ROOT,
    compression=scalping_settings.SCALPING_TICK_PARQUET_COMPRESSION,
    max_rows=scalping_settings.SCALPING_MICROSTRUCTURE_FEATURE_BUFFER_MAX_ROWS,
    flush_interval_seconds=scalping_settings.SCALPING_MICROSTRUCTURE_FEATURE_FLUSH_INTERVAL_SECONDS,
    dataset_name="microstructure_features",
)


def store_microstructure_features(
    features: MicrostructureFeatureState,
    *,
    cycle_timestamp: datetime | None = None,
) -> dict[str, Any]:
    timestamp = cycle_timestamp or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    row = features.to_flat_dict()
    row["cycle_timestamp_utc"] = timestamp.astimezone(timezone.utc).isoformat()
    return _WRITER.append(
        [row],
        partition_date=timestamp.date().isoformat(),
        symbol=features.symbol,
    )


def flush_microstructure_features() -> dict[str, Any]:
    return _WRITER.flush()
