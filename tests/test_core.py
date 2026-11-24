import pandas as pd
from vfinal.features.core import candle_features, tick_features
from vfinal.model.metrics import expected_value


def test_candle_features():
    t = pd.date_range("2026-01-01", periods=100, freq="min", tz="UTC")
    close = pd.Series(range(100), dtype=float) + 3000
    df = pd.DataFrame({"time": t, "open": close-0.2, "high": close+0.5, "low": close-0.5, "close": close, "tick_volume": 100})
    f = candle_features({"M1": df})
    assert f["m1_atr"] > 0
    assert 0 <= f["m1_rsi"] <= 100


def test_ev():
    assert expected_value(0.6, 1.0, 0.8, 0.05) > 0


def test_tick_quality_preserves_wide_spreads_and_same_timestamp_groups():
    from vfinal.data.quality import annotate_ticks, audit_ticks
    df = pd.DataFrame({
        "time_msc": [1000000, 1000050, 1000050, 1005000],
        "bid": [4300.0, 4300.1, 4300.2, 4300.3],
        "ask": [4300.3, 4300.4, 4350.2, 4300.6],
    })
    out = annotate_ticks(df)
    assert len(out) == len(df)
    assert int(out["same_timestamp_group"].sum()) == 2
    assert out["spread"].max() > 40
    assert (out["spread_regime"] == "EXTREME").any() or (out["spread_regime"] == "WIDE").any()
    assert audit_ticks(df, out)["rows"] == 4


def test_tick_quality_master_clock_handles_mixed_timestamp_formats():
    from vfinal.data.quality import annotate_ticks
    df = pd.DataFrame({
        "time_msc": [1000000, 1001000],
        "bid": [4300.0, 4300.1],
        "ask": [4300.2, 4300.3],
        "timestamp": ["2026-01-01 00:00:00+00:00", "2026-01-01T00:00:01.000Z"],
    })
    out = annotate_ticks(df)
    assert out["timestamp"].iloc[0] == "1970-01-01T00:16:40.000000Z"
