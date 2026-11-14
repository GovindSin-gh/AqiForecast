"""Fetch air quality + weather from Open-Meteo and upsert into Supabase.

python -m src.ingest.open_meteo                      # hourly job: last 2 days
python -m src.ingest.open_meteo --backfill-start 2024-01-01
"""
import argparse
import datetime as dt
import sys

import pandas as pd
import requests

from src.common import connect, load_params

AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WX_URL = "https://api.open-meteo.com/v1/forecast"
WX_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
AQ_VARS = "pm2_5,pm10,us_aqi"
WX_VARS = ("temperature_2m,relative_humidity_2m,wind_speed_10m,"
           "wind_direction_10m,surface_pressure,precipitation")
AQ_RENAME = {"pm2_5": "pm25", "pm10": "pm10", "us_aqi": "us_aqi"}
WX_RENAME = {"temperature_2m": "temp_c", "relative_humidity_2m": "rh",
             "wind_speed_10m": "wind_ms", "wind_direction_10m": "wind_dir",
             "surface_pressure": "pressure_hpa", "precipitation": "rain_mm"}
OBS_COLS = ["pm25", "pm10", "us_aqi", "temp_c", "rh", "wind_ms",
            "wind_dir", "pressure_hpa", "rain_mm"]


def _hourly(url: str, params: dict, rename: dict) -> pd.DataFrame:
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    df = pd.DataFrame(r.json()["hourly"]).rename(columns=rename)
    df["ts"] = pd.to_datetime(df.pop("time"), utc=True)   # we ask for UTC
    return df


def fetch_recent(city: dict, past_days: int = 2):
    base = {"latitude": city["lat"], "longitude": city["lon"], "timezone": "UTC"}
    aq = _hourly(AQ_URL, {**base, "hourly": AQ_VARS, "past_days": past_days,
                          "forecast_days": 2}, AQ_RENAME)
    wx = _hourly(WX_URL, {**base, "hourly": WX_VARS, "past_days": past_days,
                          "forecast_days": 1, "wind_speed_unit": "ms"}, WX_RENAME)
    now = pd.Timestamp.now(tz="UTC").floor("h")
    bench = aq.loc[aq["ts"] > now, ["ts", "pm25"]]
    obs = aq[aq["ts"] <= now].merge(wx[wx["ts"] <= now], on="ts", how="outer")
    return obs, bench, now


def fetch_range(city: dict, start: dt.date, end: dt.date) -> pd.DataFrame:
    base = {"latitude": city["lat"], "longitude": city["lon"], "timezone": "UTC",
            "start_date": start.isoformat(), "end_date": end.isoformat()}
    aq = _hourly(AQ_URL, {**base, "hourly": AQ_VARS}, AQ_RENAME)
    wx = _hourly(WX_ARCHIVE_URL, {**base, "hourly": WX_VARS, "wind_speed_unit": "ms"},
                 WX_RENAME)
    return aq.merge(wx, on="ts", how="outer")


def upsert_obs(cur, city_id: str, df: pd.DataFrame) -> int:
    df = df.dropna(subset=["pm25"]).copy()
    for c in OBS_COLS:
        if c not in df:
            df[c] = None
    rows = []
    for rec in df[["ts"] + OBS_COLS].itertuples(index=False):
        vals = [None if pd.isna(v) else float(v) for v in rec[1:]]
        rows.append([city_id, rec[0].to_pydatetime(), *vals])
    sql = (f"insert into observations (city_id, ts, {', '.join(OBS_COLS)}) "
           f"values (%s, %s, {', '.join(['%s'] * len(OBS_COLS))}) "
           "on conflict (city_id, ts) do update set "
           + ", ".join(f"{c} = excluded.{c}" for c in OBS_COLS))
    cur.executemany(sql, rows)
    return len(rows)


def upsert_bench(cur, city_id: str, issued: pd.Timestamp, bench: pd.DataFrame):
    rows = [[city_id, issued.to_pydatetime(), r.ts.to_pydatetime(),
             None if pd.isna(r.pm25) else float(r.pm25)] for r in bench.itertuples()]
    cur.executemany("insert into benchmark_forecasts (city_id, issued_at, valid_at, pm25) "
                    "values (%s, %s, %s, %s) on conflict do nothing", rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill-start", help="YYYY-MM-DD; fetch history in 30-day chunks")
    args = ap.parse_args()
    cities = load_params()["cities"]
    failures = []
    with connect() as conn, conn.cursor() as cur:
        cur.executemany("insert into cities (id, name, lat, lon) values (%s, %s, %s, %s) "
                        "on conflict (id) do nothing",
                        [[c["id"], c["name"], c["lat"], c["lon"]] for c in cities])
        conn.commit()
        for c in cities:
            try:
                if args.backfill_start:
                    d = dt.date.fromisoformat(args.backfill_start)
                    end = dt.date.today()
                    while d <= end:
                        d2 = min(d + dt.timedelta(days=29), end)
                        n = upsert_obs(cur, c["id"], fetch_range(c, d, d2))
                        conn.commit()
                        print(f"{c['id']} {d}..{d2}: {n} rows")
                        d = d2 + dt.timedelta(days=1)
                else:
                    obs, bench, now = fetch_recent(c)
                    n = upsert_obs(cur, c["id"], obs)
                    upsert_bench(cur, c["id"], now, bench)
                    conn.commit()
                    print(f"{c['id']}: {n} rows")
            except Exception as e:  # keep going; report at the end
                conn.rollback()
                failures.append(c["id"])
                print(f"FAILED {c['id']}: {e}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
