import os
from pathlib import Path

import psycopg
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_params() -> dict:
    return yaml.safe_load((ROOT / "params.yaml").read_text())


def connect() -> psycopg.Connection:
    """Use Supabase's pooler connection string (IPv4 friendly) in SUPABASE_DB_URL."""
    return psycopg.connect(os.environ["SUPABASE_DB_URL"])


def notify(msg: str) -> None:
    """Optional Discord/Slack-style webhook. Never raises."""
    url = os.getenv("ALERT_WEBHOOK_URL")
    if not url:
        return
    try:
        import requests
        requests.post(url, json={"content": msg, "text": msg}, timeout=10)
    except Exception as e:
        print("notify failed:", e)
