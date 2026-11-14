"""Hourly: grade past forecasts, compute rolling error, decide healthy / watching / alert."""
import os

from src.common import connect, load_params, notify

SCORE_SQL = """
insert into scores (city_id, ts, horizon_h, abs_err, model_version)
select f.city_id, o.ts, f.horizon_h, abs(f.p50 - o.pm25), f.model_version
from forecasts f join observations o
  on o.city_id = f.city_id and o.ts = f.issued_at + f.horizon_h * interval '1 hour'
where o.pm25 is not null and f.issued_at > now() - interval '3 days'
on conflict do nothing"""


def main():
    M = load_params()["monitor"]
    alert = False
    with connect() as conn, conn.cursor() as cur:
        cur.execute(SCORE_SQL)
        cur.execute("select version, mae from model_runs where stage='production'")
        prod = cur.fetchone()
        cur.execute("select city_id from observations group by city_id "
                    "having max(ts) < now() - make_interval(hours => %s)", (M["stale_hours"],))
        stale = [r[0] for r in cur.fetchall()]
        if prod:
            version, baseline = prod
            cur.execute("select avg(abs_err), count(*) from scores where model_version=%s "
                        "and ts > now() - interval '24 hours'", (version,))
            rolling, n = cur.fetchone()
            if n and rolling is not None and baseline:
                ratio = float(rolling) / baseline
                cur.execute("select ratio, status from monitor_log where model_version=%s "
                            "order by ts desc limit %s", (version, M["alert_hours"] - 1))
                rows = cur.fetchall()
                prev = [r[0] for r in rows]
                prior = rows[0][1] if rows else None
                hot = ratio > M["alert_ratio"]
                alert = hot and len(prev) == M["alert_hours"] - 1 and all(
                    p is not None and p > M["alert_ratio"] for p in prev)
                status = "alert" if alert else ("watching" if hot else "healthy")
                cur.execute("insert into monitor_log (model_version, rolling_mae, baseline_mae, "
                            "ratio, status, stale_cities) values (%s,%s,%s,%s,%s,%s) "
                            "on conflict (ts) do nothing",
                            (version, float(rolling), baseline, ratio, status, stale))
                if status == "alert" and prior != "alert":
                    notify(f"AQI model alert: rolling error x{ratio:.2f} of normal. Extra retrain triggered.")
                print(f"rolling MAE {rolling:.2f} vs baseline {baseline:.2f} "
                      f"(x{ratio:.2f}) -> {status}; stale cities: {stale or 'none'}")
            else:
                print("not enough scored forecasts yet")
        conn.commit()
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"alert={'true' if alert else 'false'}\n")


if __name__ == "__main__":
    main()
