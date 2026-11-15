"""Fetch air quality + weather from Open-Meteo and upsert into Supabase.

python -m src.ingest.open_meteo                       # hourly job: last 1 day
python -m src.ingest.open_meteo --backfill-start 2024-01-01
"""
import argparse
import datetime as dt
import socket
import sys
import time

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

# (connect, read) seconds. A plain tuple is what `requests` expects.
REQUEST_TIMEOUT = (10, 60)


def _create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=2,                      # a read timeout already costs 60s; don't repeat it too often
        status=3,
        backoff_factor=1.5,          # 0s, 3s, 6s ...
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": "aqi-forecast-ingest/1.0"})
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
    r = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    payload = r.json()

    items = [payload] if isinstance(payload, dict) else payload
    if len(items) != len(cities):
        raise RuntimeError(f"Expected {len(cities)} responses from {url}, got {len(items)}")

    out: dict[str, pd.DataFrame] = {}
    for city, item in zip(cities, items):
        df = pd.DataFrame(item["hourly"]).rename(columns=rename)
        df["ts"] = pd.to_datetime(df.pop("time"), utc=True)  # we ask for UTC
        out[city["id"]] = df
    return out


def _build_recent_frames(aq: pd.DataFrame, wx: pd.DataFrame | None):
    now = pd.Timestamp.now(tz="UTC").floor("h")
    bench = aq.loc[aq["ts"] > now, ["ts", "pm25"]]
    obs = aq[aq["ts"] <= now]
    if wx is not None:
        obs = obs.merge(wx[wx["ts"] <= now], on="ts", how="outer")
    return obs, bench, now


_BASE = {"timezone": "UTC"}


def _aq_params(past_days: int) -> dict:
    return {**_BASE, "hourly": AQ_VARS, "past_days": past_days, "forecast_days": 2}


def _wx_params(past_days: int) -> dict:
    return {**_BASE, "hourly": WX_VARS, "past_days": past_days,
            "forecast_days": 1, "wind_speed_unit": "ms"}


def fetch_recent(city: dict, past_days: int = 1, session: requests.Session | None = None):
    """Air quality is required; weather is optional (obs rows are still saved without it)."""
    sess = session or _create_session()
    aq = _hourly_batch(sess, AQ_URL, [city], _aq_params(past_days), AQ_RENAME)[city["id"]]
    try:
        wx = _hourly_batch(sess, WX_URL, [city], _wx_params(past_days), WX_RENAME)[city["id"]]
    except Exception as e:
        print(f"WARN {city['id']}: weather fetch failed ({e}); saving air quality only",
              file=sys.stderr)
        wx = None
    return _build_recent_frames(aq, wx)


def fetch_range(city: dict, start: dt.date, end: dt.date) -> pd.DataFrame:
    session = _create_session()
    base = {**_BASE, "start_date": start.isoformat(), "end_date": end.isoformat()}
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
           + ", ".join(f"{c} = coalesce(excluded.{c}, observations.{c})" for c in OBS_COLS))
    cur.executemany(sql, rows)
    return len(rows)


def upsert_bench(cur, city_id: str, issued: pd.Timestamp, bench: pd.DataFrame):
    rows = [[city_id, issued.to_pydatetime(), r.ts.to_pydatetime(),
             None if pd.isna(r.pm25) else float(r.pm25)] for r in bench.itertuples()]
    cur.executemany("insert into benchmark_forecasts (city_id, issued_at, valid_at, pm25) "
                    "values (%s, %s, %s, %s) on conflict do nothing", rows)


def _fetch_all_recent(session: requests.Session, cities: list[dict]) -> dict:
    """Try one batched call per API; on failure fall back to per-city fetches.
    Returns {city_id: (obs, bench, now)} - cities that fail are simply missing."""
    try:
        aq_by_id = _hourly_batch(session, AQ_URL, cities, _aq_params(1), AQ_RENAME)
        try:
            wx_by_id = _hourly_batch(session, WX_URL, cities, _wx_params(1), WX_RENAME)
        except Exception as e:
            print(f"WARN weather batch failed ({e}); saving air quality only", file=sys.stderr)
            wx_by_id = {}
        return {cid: _build_recent_frames(aq_by_id[cid], wx_by_id.get(cid)) for cid in aq_by_id}
    except Exception as e:
        print(f"Batch fetch failed ({e}), falling back to per-city fetch...", file=sys.stderr)

    results = {}
    for idx, c in enumerate(cities):
        if idx > 0:
            time.sleep(1.0)
        try:
            results[c["id"]] = fetch_recent(c, past_days=1, session=session)
        except Exception as e:
            print(f"FAILED fetch {c['id']}: {e}", file=sys.stderr)
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill-start", help="YYYY-MM-DD; fetch history in 30-day chunks")
    args = ap.parse_args()
    cities = load_params()["cities"]
    session = _create_session()
    failures = []

    recent_cache = {}
    if not args.backfill_start:
        recent_cache = _fetch_all_recent(session, cities)
        if not recent_cache:
            print("FAILED recent fetch: no city could be fetched", file=sys.stderr)
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
                    if c["id"] not in recent_cache:
                        failures.append(c["id"])
                        continue
                    obs, bench, now = recent_cache[c["id"]]
                    n = upsert_obs(cur, c["id"], obs)
                    upsert_bench(cur, c["id"], now, bench)
                    conn.commit()
                    print(f"{c['id']}: {n} rows")
            except Exception as e:  # keep going; report at the end
                conn.rollback()
                failures.append(c["id"])
                print(f"FAILED {c['id']}: {e}", file=sys.stderr)

    if failures:
        print(f"Failed cities: {failures}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
