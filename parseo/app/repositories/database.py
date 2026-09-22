from contextlib import contextmanager
import os
try:
 import psycopg
except ImportError:
 psycopg=None
@contextmanager
def connection():
 if psycopg is None: raise RuntimeError("Instale psycopg[binary]")
 with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
  yield conn
