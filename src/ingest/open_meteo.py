"""Fetch air quality + weather from Open-Meteo and upsert into Supabase.

python -m src.ingest.open_meteo                       # hourly job: last 2 days
python -m src.ingest.open_meteo --backfill-start 2024-01-01
"""
import argparse
import datetime as dt
import socket
import sys

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
import urllib3.util.connection as urllib3_cn
from urllib3.util.retry import Retry

from src.common import connect, load_params

# Force IPv4 to avoid GitHub runner IPv6 stalls to Cloudflare-fronted APIs
urllib3_cn.allowed_gai_family = lambda: socket.AF_INET

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


def _create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=2,  # 2s, 4s, 8s, 16s
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session


def _hourly_batch(
    session: requests.Session,
    url: str,
    cities: list[dict],
    extra_params: dict,
    rename: dict,
) -> dict[str, pd.DataFrame]:
    params = {
        "latitude": ",".join(str(c["lat"]) for c in cities),
        "longitude": ",".join(str(c["lon"]) for c in cities),
        **extra_params,
    }
    r = session.get(url, params=params, timeout=(10, 60))
    r.raise_for_status()
    payload = r.json()

    # Open-Meteo returns a single dict for 1 location, or a list of dicts for multiple.
    items = [payload] if isinstance(payload, dict) else payload
    if len(items) != len(cities):
        raise RuntimeError(f"Expected {len(cities)} responses from {url}, got {len(items)}")

    out: dict[str, pd.DataFrame] = {}
    for city, item in zip(cities, items):
        df = pd.DataFrame(item["hourly"]).rename(columns=rename)
        df["ts"] = pd.to_datetime(df.pop("time"), utc=True)  # we ask for UTC
        out[city["id"]] = df
    return out


def _hourly(url: str, params: dict, rename: dict) -> pd.DataFrame:
    city = {"id": "_single", "lat": params["latitude"], "lon": params["longitude"]}
    rest = {k: v for k, v in params.items() if k not in ("latitude", "longitude")}
    return _hourly_batch(_create_session(), url, [city], rest, rename)["_single"]


def _build_recent_frames(aq: pd.DataFrame, wx: pd.DataFrame):
    now = pd.Timestamp.now(tz="UTC").floor("h")
    bench = aq.loc[aq["ts"] > now, ["ts", "pm25"]]
    obs = aq[aq["ts"] <= now].merge(wx[wx["ts"] <= now], on="ts", how="outer")
    return obs, bench, now


def fetch_recent(city: dict, past_days: int = 2):
    session = _create_session()
    base = {"timezone": "UTC"}
    aq = _hourly_batch(
        session, AQ_URL, [city],
        {**base, "hourly": AQ_VARS, "past_days": past_days, "forecast_days": 2},
        AQ_RENAME,
    )[city["id"]]
    wx = _hourly_batch(
        session, WX_URL, [city],
        {**base, "hourly": WX_VARS, "past_days": past_days, "forecast_days": 1, "wind_speed_unit": "ms"},
        WX_RENAME,
    )[city["id"]]
    return _build_recent_frames(aq, wx)


def fetch_range(city: dict, start: dt.date, end: dt.date) -> pd.DataFrame:
    session = _create_session()
    base = {"timezone": "UTC", "start_date": start.isoformat(), "end_date": end.isoformat()}
    aq = _hourly_batch(session, AQ_URL, [city], {**base, "hourly": AQ_VARS}, AQ_RENAME)[city["id"]]
    wx = _hourly_batch(
        session, WX_ARCHIVE_URL, [city],
        {**base, "hourly": WX_VARS, "wind_speed_unit": "ms"},
        WX_RENAME,
    )[city["id"]]
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
    session = _create_session()
    failures = []

    try:
        if not args.backfill_start:
            base = {"timezone": "UTC"}
            aq_by_id = _hourly_batch(
                session, AQ_URL, cities,
                {**base, "hourly": AQ_VARS, "past_days": 2, "forecast_days": 2},
                AQ_RENAME,
            )
            wx_by_id = _hourly_batch(
                session, WX_URL, cities,
                {**base, "hourly": WX_VARS, "past_days": 2, "forecast_days": 1, "wind_speed_unit": "ms"},
                WX_RENAME,
            )
    except Exception as e:
        print(f"FAILED batch fetch: {e}", file=sys.stderr)
        return 1

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
                    obs, bench, now = _build_recent_frames(aq_by_id[c["id"]], wx_by_id[c["id"]])
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
