"""Feature code shared by training, the hourly jobs and the API.
One implementation means training and serving can never disagree."""
import numpy as np
import pandas as pd

RAW_COLS = ["pm25", "pm10", "temp_c", "rh", "wind_ms", "wind_dir", "pressure_hpa", "rain_mm"]
FEATURES = ["pm25", "pm10", "temp_c", "rh", "wind_ms", "wind_sin", "wind_cos",
            "pressure_hpa", "rain_mm", "hour_sin", "hour_cos", "doy_sin", "doy_cos"]
assert FEATURES[0] == "pm25"   # the target is column 0
WINDOW, HORIZON = 48, 24


def clean_city_frame(df: pd.DataFrame) -> pd.DataFrame:
    """df: columns ts (UTC) + RAW_COLS. Returns a strict hourly frame; gaps of up to
    3 hours are interpolated, longer gaps stay NaN (and those windows are dropped)."""
    if df.empty:
        raise ValueError("no observations")
    d = df.sort_values("ts").drop_duplicates("ts").set_index("ts")[RAW_COLS].astype("float64")
    d.index = pd.DatetimeIndex(d.index)
    full = pd.date_range(d.index.min(), d.index.max(), freq="h")
    return d.reindex(full).interpolate(limit=3, limit_area="inside")


def add_features(d: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=d.index)
    for c in ["pm25", "pm10", "temp_c", "rh", "wind_ms", "pressure_hpa", "rain_mm"]:
        out[c] = d[c]
    rad = np.deg2rad(d["wind_dir"])
    out["wind_sin"], out["wind_cos"] = np.sin(rad), np.cos(rad)
    hour, doy = d.index.hour, d.index.dayofyear
    out["hour_sin"], out["hour_cos"] = np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)
    out["doy_sin"], out["doy_cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
    return out[FEATURES]


def latest_window(df: pd.DataFrame, window: int = WINDOW):
    """Newest `window` hours for one city -> (array (window, F), last timestamp)."""
    d = clean_city_frame(df).iloc[-window:]
    if len(d) < window or d.isna().any().any():
        raise ValueError("not enough clean recent data for this city")
    return add_features(d).to_numpy(np.float32), d.index[-1]


def make_scaler(X_train: np.ndarray, cities: list[str]) -> dict:
    """Mean/std from TRAIN rows only, so test data never influences scaling."""
    flat = X_train.reshape(-1, X_train.shape[-1])
    mean, std = flat.mean(0), flat.std(0)
    std[std < 1e-6] = 1.0
    return {"features": FEATURES, "mean": mean.tolist(), "std": std.tolist(),
            "cities": cities, "window": WINDOW, "horizon": HORIZON}


def normalize(X: np.ndarray, scaler: dict) -> np.ndarray:
    mean = np.asarray(scaler["mean"], dtype=np.float32)
    std = np.asarray(scaler["std"], dtype=np.float32)
    return ((X - mean) / std).astype(np.float32)


def y_stats(scaler: dict):
    return float(scaler["mean"][0]), float(scaler["std"][0])
