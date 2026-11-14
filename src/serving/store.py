"""Database reads shared by the API and the hourly jobs."""
import pandas as pd

from src.features.transform import RAW_COLS


def fetch_recent(conn, city_id: str | None = None, hours: int = 72) -> pd.DataFrame:
    sql = ("select city_id, ts, " + ", ".join(RAW_COLS) + " from observations "
           "where ts >= now() - make_interval(hours => %s)")
    args = [hours]
    if city_id:
        sql += " and city_id = %s"
        args.append(city_id)
    with conn.cursor() as cur:
        cur.execute(sql + " order by city_id, ts", args)
        cols = [d.name for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def production_version(conn) -> str | None:
    with conn.cursor() as cur:
        cur.execute("select version from model_runs where stage='production'")
        r = cur.fetchone()
        return r[0] if r else None


def load_production(conn) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("select m.version, m.mae, a.onnx, a.scaler from model_runs m "
                    "join model_artifacts a using (version) where m.stage='production'")
        r = cur.fetchone()
    return {"version": r[0], "mae": r[1], "onnx": bytes(r[2]), "scaler": r[3]} if r else None
