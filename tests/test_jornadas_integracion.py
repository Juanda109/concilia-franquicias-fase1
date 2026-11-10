import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.database import connection


@pytest.fixture
def db_connection():
    with connection() as conn:
        yield conn


def test_postgresql_disponible(db_connection):
    with db_connection.cursor() as cur:
        cur.execute("SELECT current_database(), current_user")
        resultado = cur.fetchone()

    assert resultado[0] == os.environ["DB_NAME"]
    assert resultado[1] == "concilia_app"


def test_tablas_jornada_disponibles(db_connection):
    with db_connection.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN (
                  'con_jornada',
                  'con_insumo_esperado',
                  'con_catalogo_insumo'
              )
        """)
        total = cur.fetchone()[0]

    assert total == 3


def test_vista_jornada_disponible(db_connection):
    with db_connection.cursor() as cur:
        cur.execute("""
            SELECT to_regclass('public.vw_con_jornada_insumos')
        """)
        resultado = cur.fetchone()[0]

    assert resultado is not None


