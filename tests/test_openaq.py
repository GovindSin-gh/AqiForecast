import pandas as pd

from src.validation.openaq import compare, hours_to_series, pm25_sensors

LOC = {"results": [
    {"sensors": [{"id": 11, "parameter": {"id": 2, "name": "pm25"}},
                 {"id": 12, "parameter": {"id": 7, "name": "no2"}}]},
    {"sensors": [{"id": 21, "parameter": {"name": "pm25"}}]}]}


def row(v, t="2026-11-13T10:00:00Z"):
    return {"value": v, "period": {"datetimeFrom": {"utc": t}}}


def test_only_pm25_sensors_are_kept():
    assert pm25_sensors(LOC) == [11, 21]


def test_bad_values_are_dropped():
    s = hours_to_series({"results": [row(50.0), row(-999, "2026-11-13T11:00:00Z"),
                                      row(None, "2026-11-13T12:00:00Z"), row(5000, "2026-11-13T13:00:00Z")]})
    assert len(s) == 1 and s.iloc[0] == 50.0


def test_compare_needs_enough_overlap():
    idx = pd.date_range("2026-01-01", periods=30, freq="h", tz="UTC")
    m, g = pd.Series(range(30), index=idx, dtype=float), pd.Series(range(30), index=idx, dtype=float) + 2
    r = compare(m, g)
    assert r["n"] == 30 and abs(r["bias"] + 2) < 1e-9 and r["mae"] == 2
    assert compare(m.iloc[:5], g.iloc[:5]) is None
