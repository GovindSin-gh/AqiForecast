"""Dump observations from Supabase to a parquet file that DVC versions."""
import pandas as pd

from src.common import ROOT, connect


def main():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select city_id, ts, pm25, pm10, temp_c, rh, wind_ms, wind_dir, "
                    "pressure_hpa, rain_mm from observations order by city_id, ts")
        cols = [d.name for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    out = ROOT / "data/raw/observations.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"exported {len(df)} rows to {out}")


if __name__ == "__main__":
    main()
