"""Preflight check. Run it after each setup step to see what is still missing.

python -m scripts.check_setup [--api-url https://your-api.onrender.com] [--test-llm]
"""
import argparse
import os

import requests

TABLES = ["cities", "observations", "benchmark_forecasts", "model_runs", "model_artifacts",
          "forecasts", "scores", "monitor_log", "ground_truth", "validation_log"]


def line(ok, name, detail=""):
    print(("\u2714 " if ok else "\u2716 ") + name + (f"   {detail}" if detail else ""))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url")
    ap.add_argument("--test-llm", action="store_true", help="makes one small Groq call")
    a = ap.parse_args()

    if os.getenv("SUPABASE_DB_URL"):
        try:
            from src.common import connect
            with connect() as conn, conn.cursor() as cur:
                line(True, "Database connection")
                cur.execute("select table_name from information_schema.tables "
                            "where table_schema='public'")
                have = {r[0] for r in cur.fetchall()}
                missing = [t for t in TABLES if t not in have]
                line(not missing, "Tables created", ("missing: " + ", ".join(missing)) if missing
                     else "", )
                if not missing:
                    for t, label in [("observations", "observation rows"), ("forecasts", "forecast rows"),
                                     ("ground_truth", "OpenAQ rows")]:
                        cur.execute(f"select count(*) from {t}")
                        print(f"    {label}: {cur.fetchone()[0]}")
                    cur.execute("select version from model_runs where stage='production'")
                    r = cur.fetchone()
                    line(bool(r), "Production model", r[0] if r else "none yet: run the retrain workflow")
        except Exception as e:
            line(False, "Database connection", str(e)[:150])
    else:
        line(False, "SUPABASE_DB_URL is set")

    try:
        r = requests.get("https://air-quality-api.open-meteo.com/v1/air-quality",
                         params={"latitude": 26.85, "longitude": 80.95, "hourly": "pm2_5"}, timeout=20)
        line(r.ok, "Open-Meteo reachable", str(r.status_code))
    except Exception as e:
        line(False, "Open-Meteo reachable", str(e)[:100])

    key = os.getenv("OPENAQ_API_KEY")
    if key:
        try:
            r = requests.get("https://api.openaq.org/v3/locations", params={"limit": 1},
                             headers={"X-API-Key": key}, timeout=20)
            line(r.ok, "OpenAQ key works", str(r.status_code))
        except Exception as e:
            line(False, "OpenAQ key works", str(e)[:100])
    else:
        line(False, "OPENAQ_API_KEY is set", "optional: only validation needs it")

    line(bool(os.getenv("GROQ_API_KEY")), "GROQ_API_KEY is set", "optional: Explain button falls back to a template")
    if a.test_llm and os.getenv("GROQ_API_KEY"):
        from api.explain import narrate
        out = narrate({"city": "Test", "when": "in the next hour", "aqi_p50": 100, "aqi_p10": 90,
                       "aqi_p90": 110, "category": "Moderate", "trend": "steady"})
        line(out["source"] == "llm", "Groq / Qwen call", out["text"][:100])

    if a.api_url:
        base = a.api_url.rstrip("/")
        for path in ("/health", "/ready", "/summary"):
            try:
                r = requests.get(base + path, timeout=90)   # free hosting may need time to wake
                line(r.ok, f"API {path}", str(r.status_code))
            except Exception as e:
                line(False, f"API {path}", str(e)[:100])


if __name__ == "__main__":
    main()
