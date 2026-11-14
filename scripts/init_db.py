"""python -m scripts.init_db : create all tables (safe to run again)."""
from src.common import ROOT, connect


def main():
    with connect() as conn, conn.cursor() as cur:
        cur.execute((ROOT / "db/schema.sql").read_text())
        conn.commit()
    print("database schema is ready")


if __name__ == "__main__":
    main()
