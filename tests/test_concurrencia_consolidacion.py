"""Exclusion mutua entre procesamiento y consolidacion."""

import os

import pytest
from psycopg.errors import LockNotAvailable

from app.repositories.database import connection


def test_exclusion_mutua_jornada_294():
    """Prueba bloqueo de una jornada existente, sin depender del ID 294.

    Se utiliza una fila ya existente; no se modifica su contenido.
    """
    if os.getenv("DB_NAME") != "concilia_test":
        pytest.skip("Requiere concilia_test")

    with connection() as conn1:
        try:
            with connection() as conn2:
                try:
                    with conn1.cursor() as cur1, conn2.cursor() as cur2:
                        for cur in (cur1, cur2):
                            cur.execute("SELECT current_database()")
                            assert cur.fetchone()[0] == "concilia_test"
                        cur1.execute("SET LOCAL lock_timeout = '5s'")
                        cur2.execute("SET LOCAL lock_timeout = '1s'")
                        cur1.execute("""SELECT id_jornada FROM con_jornada
                                        ORDER BY id_jornada LIMIT 1 FOR UPDATE""")
                        fila = cur1.fetchone()
                        if fila is None:
                            pytest.skip("No hay jornada existente para probar bloqueo")
                        jornada = fila[0]
                        cur2.execute("SAVEPOINT prueba_concurrencia")
                        bloqueado = False
                        try:
                            cur2.execute("""SELECT id_jornada FROM con_jornada
                                            WHERE id_jornada=%s FOR UPDATE NOWAIT""",
                                         (jornada,))
                        except LockNotAvailable as exc:
                            assert exc.sqlstate == "55P03"
                            bloqueado = True
                            cur2.execute("ROLLBACK TO SAVEPOINT prueba_concurrencia")
                        assert bloqueado
                finally:
                    conn2.rollback()
        finally:
            conn1.rollback()
