"""Hourly: forecast every city with the production model and store the result,
so score.py can grade it once the real values arrive."""
import datetime as dt

from src.common import connect, load_params
from src.features.transform import latest_window
from src.serving.predictor import OnnxPredictor
from src.serving.store import fetch_recent, load_production


def main():
    P = load_params()
    stale = dt.timedelta(hours=P["monitor"]["stale_hours"])
    with connect() as conn:
        prod = load_production(conn)
        if not prod:
            print("no production model yet; nothing to predict")
            return
        pred = OnnxPredictor(prod["onnx"], prod["scaler"])
        cities = prod["scaler"]["cities"]
        df = fetch_recent(conn, hours=72)
        rows = []
        for cid, g in df.groupby("city_id"):
            if cid not in cities:
                continue
            try:
                X, last_ts = latest_window(g)
            except ValueError as e:
                print(f"skip {cid}: {e}")
                continue
            if dt.datetime.now(dt.timezone.utc) - last_ts.to_pydatetime() > stale:
                print(f"skip {cid}: data is stale")
                continue
            out = pred.predict(X[None], [cities.index(cid)])[0]
            for h, (p10, p50, p90) in enumerate(out, start=1):
                rows.append((cid, last_ts.to_pydatetime(), h, float(p10), float(p50),
                             float(p90), prod["version"]))
        with conn.cursor() as cur:
            cur.executemany("insert into forecasts (city_id, issued_at, horizon_h, p10, p50, p90, "
                            "model_version) values (%s,%s,%s,%s,%s,%s,%s) on conflict do nothing", rows)
        conn.commit()
        print(f"stored {len(rows)} forecast rows ({prod['version']})")


if __name__ == "__main__":
    main()
