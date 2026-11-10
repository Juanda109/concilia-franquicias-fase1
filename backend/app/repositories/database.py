import os
from contextlib import contextmanager

import psycopg


@contextmanager
def connection():
    """Proporciona una conexión PostgreSQL."""
    conn = psycopg.connect(
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=5,
    )

    try:
        with conn:
            yield conn
    finally:
        conn.close()
