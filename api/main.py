import logging
import os
import time
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.db import connect
from api.explain import narrate
from api.ratelimit import RateLimiter
from src.common import load_params
from src.features.aqi import category, pm25_to_aqi
from src.features.transform import latest_window
from src.serving import store
from src.serving.predictor import OnnxPredictor

P = load_params()
CITIES = {c["id"]: c for c in P["cities"]}
STALE = timedelta(hours=P["monitor"]["stale_hours"])

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("api")
ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
if os.getenv("ENV") == "production" and (not os.getenv("ALLOWED_ORIGINS") or "*" in ORIGINS):
    raise RuntimeError("Set ALLOWED_ORIGINS to your site URL(s) in production (no '*').")
EXPLAIN_LIMIT = RateLimiter(limit=int(os.getenv("EXPLAIN_PER_MINUTE", "6")), window=60)
CACHED = {"summary", "forecast", "history", "cities", "validation"}

app = FastAPI(title="AQI Forecast API")
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"])


@app.middleware("http")
async def common_headers(request: Request, call_next):
    t0 = time.time()
    resp = await call_next(request)
    first = request.url.path.split("/")[1]
    if request.method == "GET" and first in CACHED:
        resp.headers["Cache-Control"] = "public, max-age=60"
    else:
        resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    log.info("%s %s %s %.0fms", request.method, request.url.path, resp.status_code, (time.time() - t0) * 1000)
    return resp


@app.exception_handler(psycopg.Error)
async def db_error(request: Request, exc: psycopg.Error):
    log.error("database error: %s", exc)
    return JSONResponse({"detail": "database temporarily unavailable"}, status_code=503)

STATE = {"version": None, "pred": None, "scaler": None, "checked": 0.0}
EXPLAIN_CACHE: dict = {}


def iso(t) -> str | None:
    return t.astimezone(timezone.utc).isoformat() if t else None


def predictor(conn):
    if time.time() - STATE["checked"] > 300 or STATE["pred"] is None:
        STATE["checked"] = time.time()
        if store.production_version(conn) != STATE["version"]:
            prod = store.load_production(conn)
            if prod:
                STATE.update(version=prod["version"], scaler=prod["scaler"],
                             pred=OnnxPredictor(prod["onnx"], prod["scaler"]))
    if STATE["pred"] is None:
        raise HTTPException(503, "No production model yet. Run the retrain workflow first.")
    return STATE["pred"], STATE["scaler"], STATE["version"]


def city_or_404(city: str):
    if city not in CITIES:
        raise HTTPException(404, f"unknown city '{city}'")
    return CITIES[city]


def build_forecast(city: str, horizon: int):
    city_or_404(city)
    with connect() as conn:
        pred, scaler, version = predictor(conn)
        df = store.fetch_recent(conn, city, hours=72)
    try:
        X, last_ts = latest_window(df)
    except ValueError as e:
        raise HTTPException(503, str(e))
    out = pred.predict(X[None], [scaler["cities"].index(city)])[0]
    pts = []
    for h in range(1, horizon + 1):
        p10, p50, p90 = (float(v) for v in out[h - 1])
        pts.append({"h": h, "valid_at": iso(last_ts.to_pydatetime() + timedelta(hours=h)),
                    "pm25_p10": round(p10, 1), "pm25_p50": round(p50, 1), "pm25_p90": round(p90, 1),
                    "aqi_p10": pm25_to_aqi(p10), "aqi_p50": pm25_to_aqi(p50),
                    "aqi_p90": pm25_to_aqi(p90), "category": category(pm25_to_aqi(p50))})
    stale = datetime.now(timezone.utc) - last_ts.to_pydatetime() > STALE
    weather = {k: float(df.sort_values("ts").iloc[-1][k]) for k in ("temp_c", "rh", "wind_ms")
               if len(df) and df.sort_values("ts").iloc[-1][k] == df.sort_values("ts").iloc[-1][k]}
    return {"city": city, "issued_at": iso(last_ts.to_pydatetime()), "model_version": version,
            "stale": stale, "points": pts}, weather


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select 1")
    return {"status": "ready"}


@app.get("/validation")
def validation():
    """Latest comparison of model-based values with OpenAQ ground stations."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select distinct on (city_id) city_id, ts, n, mae, bias, corr, n_sensors "
                    "from validation_log order by city_id, ts desc")
        return [{"city": r[0], "checked_at": iso(r[1]), "hours": r[2], "mae": r[3], "bias": r[4],
                 "corr": r[5], "stations": r[6]} for r in cur.fetchall()]


@app.get("/cities")
def cities():
    return list(CITIES.values())


@app.get("/history/{city}")
def history(city: str, hours: int = Query(48, ge=1, le=168)):
    city_or_404(city)
    with connect() as conn:
        df = store.fetch_recent(conn, city, hours=hours)
    pts = [{"ts": iso(r.ts.to_pydatetime()),
            "pm25": None if r.pm25 != r.pm25 else round(float(r.pm25), 1),
            "aqi": None if r.pm25 != r.pm25 else pm25_to_aqi(r.pm25)} for r in df.itertuples()]
    return {"city": city, "points": pts}


@app.get("/forecast/{city}")
def forecast(city: str, horizon: int = Query(24, ge=1, le=24)):
    return build_forecast(city, horizon)[0]


@app.get("/summary")
def summary():
    """Cheap map data: latest reading + the forecast the hourly job stored."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select distinct on (city_id) city_id, pm25 from observations "
                    "where pm25 is not null order by city_id, ts desc")
        now = dict(cur.fetchall())
        cur.execute("with l as (select distinct on (city_id) city_id, issued_at from forecasts "
                    "order by city_id, issued_at desc) "
                    "select f.city_id, f.horizon_h, f.p50 from forecasts f "
                    "join l on l.city_id = f.city_id and l.issued_at = f.issued_at")
        fc: dict = {}
        for cid, h, p50 in cur.fetchall():
            fc.setdefault(cid, {})[h] = p50

    def cell(pm):
        if pm is None:
            return None
        a = pm25_to_aqi(pm)
        return {"aqi": a, "category": category(a)}

    out = []
    for cid, c in CITIES.items():
        f = fc.get(cid, {})
        out.append({**c, "now": cell(now.get(cid)), "next_hour": cell(f.get(1)),
                    "peak_24h": cell(max(f.values()) if f else None)})
    return out


@app.get("/model/health")
def model_health():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select version, mae, promoted_at from model_runs where stage='production'")
        prod = cur.fetchone()
        cur.execute("select ts, ratio, status, drift_flag, stale_cities, rolling_mae, baseline_mae "
                    "from monitor_log order by ts desc limit 48")
        log = cur.fetchall()
        cur.execute("select version, stage, created_at from model_runs "
                    "order by created_at desc limit 5")
        runs = cur.fetchall()
        cur.execute("select max(ts) from observations")
        last_ingest = cur.fetchone()[0]
    latest = log[0] if log else None
    return {
        "model_version": prod[0] if prod else None,
        "status": latest[2] if latest else "no data yet",
        "ratio": latest[1] if latest else None,
        "rolling_mae_24h": latest[5] if latest else None,
        "baseline_mae": latest[6] if latest else None,
        "drift_flag": bool(latest[3]) if latest else False,
        "stale_cities": (latest[4] or []) if latest else [],
        "last_ingest": iso(last_ingest),
        "last_promotion": iso(prod[2]) if prod else None,
        "recent": [{"ts": iso(r[0]), "ratio": r[1]} for r in reversed(log)],
        "runs": [{"version": r[0], "stage": r[1], "created_at": iso(r[2])} for r in runs]}


class ExplainIn(BaseModel):
    city: str
    horizon: int = 24


@app.post("/explain")
def explain(body: ExplainIn, request: Request):
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?")
    if not EXPLAIN_LIMIT.check(ip):
        raise HTTPException(429, "Too many explain requests. Please wait a minute.")
    horizon = 1 if body.horizon == 1 else 24
    fc, weather = build_forecast(body.city, horizon)
    key = (body.city, fc["issued_at"], horizon, fc["model_version"])
    if key not in EXPLAIN_CACHE:                    # saves free-tier LLM quota
        pts = fc["points"]
        pick = pts[0] if horizon == 1 else max(pts, key=lambda p: p["pm25_p50"])
        first, last = pts[0]["pm25_p50"], pts[-1]["pm25_p50"]
        trend = "rising" if last > first * 1.1 else "falling" if last < first * 0.9 else "steady"
        facts = {"city": CITIES[body.city]["name"],
                 "when": "in the next hour" if horizon == 1 else f"at its peak, about {pick['h']} hours from now",
                 "aqi_p50": pick["aqi_p50"], "aqi_p10": pick["aqi_p10"], "aqi_p90": pick["aqi_p90"],
                 "category": pick["category"], "trend": trend, **weather}
        if len(EXPLAIN_CACHE) > 200:
            EXPLAIN_CACHE.clear()
        EXPLAIN_CACHE[key] = narrate(facts)
    return EXPLAIN_CACHE[key]
