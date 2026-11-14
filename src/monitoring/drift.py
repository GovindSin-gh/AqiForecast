"""Weekly-style drift check: last 7 days vs the 60 days before.
Heuristic: KS test per column. Hourly data is autocorrelated, so p-values look more
significant than they are; treat the flag as 'go look', not as proof.
Writes an Evidently HTML report as a bonus when Evidently is installed."""
import json

import pandas as pd
from scipy.stats import ks_2samp

from src.common import ROOT, connect

COLS = ["pm25", "pm10", "temp_c", "rh", "wind_ms", "pressure_hpa"]


def main():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select ts, " + ", ".join(COLS) + " from observations "
                    "where ts >= now() - interval '67 days'")
        df = pd.DataFrame(cur.fetchall(), columns=["ts"] + COLS)
        if df.empty:
            print("no data")
            return
        cut = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)
        cur_df, ref_df = df[df["ts"] >= cut], df[df["ts"] < cut]
        res = {}
        for c in COLS:
            a, b = ref_df[c].dropna(), cur_df[c].dropna()
            if len(a) > 50 and len(b) > 50:
                res[c] = float(ks_2samp(a, b).pvalue)
        flag = sum(p < 0.01 for p in res.values()) >= 3
        (ROOT / "reports").mkdir(exist_ok=True)
        (ROOT / "reports/drift.json").write_text(json.dumps({"p_values": res, "drift": flag}))
        cur.execute("update monitor_log set drift_flag=%s where ts=(select max(ts) from monitor_log)",
                    (flag,))
        conn.commit()
        print("drift flag:", flag, res)
    try:  # optional; Evidently's API changes between versions
        from evidently import Report
        from evidently.presets import DataDriftPreset
        Report([DataDriftPreset()]).run(current_data=cur_df[COLS], reference_data=ref_df[COLS]) \
            .save_html(str(ROOT / "reports/drift.html"))
    except Exception as e:
        print("evidently report skipped:", e)


if __name__ == "__main__":
    main()
