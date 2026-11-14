"""Ground-truth check against real stations via OpenAQ (API v3).

Needs OPENAQ_API_KEY (free key; check OpenAQ's docs for current limits and endpoints).
Flow: find nearby PM2.5 sensors -> fetch hourly values -> average per hour -> store in
ground_truth -> compare with the model-based values we hold -> store in validation_log.
This is validation only. The OpenAQ values are never used to train the model.
"""
import datetime as dt
import os
import sys
import time

import pandas as pd
import requests

from src.common import connect, load_params

BASE = "https://api.openaq.org/v3"
RADIUS_M = 25000
MAX_SENSORS = 3
PM25_PARAM_ID = 2


def _get(path: str, params: dict) -> dict:
    headers = {"X-API-Key": os.environ["OPENAQ_API_KEY"]}
    for attempt in range(3):
        r = requests.get(BASE + path, params=params, headers=headers, timeout=30)
        if r.status_code == 429:                      # rate limited: wait and retry
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("OpenAQ rate limit hit; try again later")


def pm25_sensors(locations: dict, limit: int = MAX_SENSORS) -> list[int]:
    ids = []
    for loc in locations.get("results", []):
        for s in loc.get("sensors", []):
            if (s.get("parameter") or {}).get("name") == "pm25":
                ids.append(s["id"])
    return ids[:limit]


def hours_to_series(payload: dict) -> pd.Series:
    out = {}
    for r in payload.get("results", []):
        t = ((r.get("period") or {}).get("datetimeFrom") or {}).get("utc")
        v = r.get("value")
        if t is None or v is None or v < 0 or v > 1000:   # drop sentinel / absurd values
            continue
        out[pd.to_datetime(t, utc=True).floor("h")] = float(v)
    return pd.Series(out, dtype="float64")


def compare(model: pd.Series, ground: pd.Series, min_n: int = 24) -> dict | None:
    d = pd.concat([model, ground], axis=1, keys=["m", "g"]).dropna()
    if len(d) < min_n:
        return None
    corr = d["m"].corr(d["g"])
    return {"n": int(len(d)), "mae": float((d["m"] - d["g"]).abs().mean()),
            "bias": float((d["m"] - d["g"]).mean()),
            "corr": None if pd.isna(corr) else float(corr)}


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    if not os.getenv("OPENAQ_API_KEY"):
        print("OPENAQ_API_KEY is not set; skipping validation")
        return 0
    now = dt.datetime.now(dt.timezone.utc)
    start = now - dt.timedelta(days=7)
    failures = []
    with connect() as conn, conn.cursor() as cur:
        for c in load_params()["cities"]:
            try:
                locs = _get("/locations", {"coordinates": f"{c['lat']},{c['lon']}",
                                           "radius": RADIUS_M, "parameters_id": PM25_PARAM_ID,
                                           "limit": 20})
                ids = pm25_sensors(locs)
                series = []
                for sid in ids:
                    s = hours_to_series(_get(f"/sensors/{sid}/hours", {
                        "datetime_from": _iso(start), "datetime_to": _iso(now), "limit": 1000}))
                    if len(s):
                        series.append(s)
                    time.sleep(0.5)
                if not series:
                    print(f"{c['id']}: no PM2.5 stations with data nearby")
                    continue
                df = pd.concat(series, axis=1)
                gt, cnt = df.mean(axis=1), df.count(axis=1)
                cur.executemany(
                    "insert into ground_truth (city_id, ts, pm25, n_sensors) values (%s,%s,%s,%s) "
                    "on conflict (city_id, ts) do update set pm25=excluded.pm25, n_sensors=excluded.n_sensors",
                    [(c["id"], t.to_pydatetime(), float(v), int(cnt[t])) for t, v in gt.dropna().items()])
                cur.execute("select o.ts, o.pm25, g.pm25 from observations o join ground_truth g "
                            "on g.city_id = o.city_id and g.ts = o.ts "
                            "where o.city_id=%s and o.ts > now() - interval '30 days' "
                            "and o.pm25 is not null", (c["id"],))
                rows = cur.fetchall()
                res = compare(pd.Series({r[0]: r[1] for r in rows}, dtype="float64"),
                              pd.Series({r[0]: r[2] for r in rows}, dtype="float64"))
                if res:
                    cur.execute("insert into validation_log (city_id, n, mae, bias, corr, n_sensors) "
                                "values (%s,%s,%s,%s,%s,%s)",
                                (c["id"], res["n"], res["mae"], res["bias"], res["corr"], len(series)))
                    print(f"{c['id']}: n={res['n']} gap={res['mae']:.1f} bias={res['bias']:+.1f} corr={res['corr']}")
                else:
                    print(f"{c['id']}: too few overlapping hours to compare yet")
                conn.commit()
            except Exception as e:
                conn.rollback()
                failures.append(c["id"])
                print(f"FAILED {c['id']}: {e}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
