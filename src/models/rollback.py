"""python -m src.models.rollback : put the previous model back into production."""
from src.common import connect


def main():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select version from model_runs where stage='archived' "
                    "order by promoted_at desc limit 1")
        row = cur.fetchone()
        if not row:
            raise SystemExit("no archived model to roll back to")
        cur.execute("update model_runs set stage='rolled_back' where stage='production'")
        cur.execute("update model_runs set stage='production' where version=%s", (row[0],))
        conn.commit()
        print("production is now", row[0])


if __name__ == "__main__":
    main()
