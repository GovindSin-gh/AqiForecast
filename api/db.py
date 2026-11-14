"""Small connection pool. Works with Supabase's session pooler string.
prepare_threshold=None also keeps it safe with the transaction pooler (port 6543)."""
import os

from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(os.environ["SUPABASE_DB_URL"], min_size=1, max_size=5,
                               timeout=10, open=True, kwargs={"prepare_threshold": None})
    return _pool


def connect():
    return pool().connection()      # use as: with connect() as conn:
