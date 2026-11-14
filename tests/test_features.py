import numpy as np
import pandas as pd
import pytest

from src.features.aqi import category, pm25_to_aqi
from src.features.transform import FEATURES, RAW_COLS, add_features, latest_window


def frame(n=60, gap_at=None):
    ts = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
    df = pd.DataFrame({c: np.linspace(10, 20, n) for c in RAW_COLS})
    df["wind_dir"] = 90.0
    df.insert(0, "ts", ts)
    if gap_at is not None:
        df = df.drop(index=range(gap_at, gap_at + 6))
    return df


def test_window_uses_only_newest_rows():
    X, last = latest_window(frame())
    assert X.shape == (48, len(FEATURES)) and last == pd.Timestamp("2026-01-03 11:00", tz="UTC")


def test_short_history_raises():
    with pytest.raises(ValueError):
        latest_window(frame(n=30))


def test_long_gap_raises():
    with pytest.raises(ValueError):
        latest_window(frame(n=60, gap_at=40))


def test_features_are_finite():
    from src.features.transform import clean_city_frame
    assert np.isfinite(add_features(clean_city_frame(frame())).to_numpy()).all()


def test_aqi_boundaries():
    assert pm25_to_aqi(0) == 0 and pm25_to_aqi(9.1) == 51 and pm25_to_aqi(9999) == 500
    assert category(50) == "Good" and category(151) == "Unhealthy"
