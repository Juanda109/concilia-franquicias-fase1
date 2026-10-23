from datetime import date, timedelta
import hashlib
from fabricas_archivos import generar_ha22_valido
import os
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api import archivos as archivos_api
from app.api import jornadas as jornadas_api
from app.repositories.database import connection as real_connection




def fecha_prueba(desplazamiento):
    from datetime import date, timedelta

    from app.repositories.database import connection

    inicio = date.today() + timedelta(days=desplazamiento)

    if not (2000 <= inicio.year <= 2068):
        raise RuntimeError("Fecha fuera del rango FAAMMDD")

    with connection() as conn:
        with conn.cursor() as cur:
            fecha = inicio

            while fecha.year <= 2068:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1
                        FROM con_jornada
                        WHERE fecha_contable = %s
                    )
                """, (fecha,))

                if not cur.fetchone()[0]:
                    return fecha

                fecha += timedelta(days=1)

    raise RuntimeError("No hay fechas de prueba disponibles")


def nombre_ha22(fecha):
    return f"DESCARHA22_F{fecha:%y%m%d}.TXT"


@pytest.fixture
def entorno_archivos(monkeypatch, tmp_path):
    if os.environ.get("DB_NAME") != "concilia_test":
        pytest.fail("Las pruebas requieren concilia_test")

    with real_connection() as conn:
        if conn.info.dbname != "concilia_test":
            pytest.fail("Conexion no autorizada")

        with conn.transaction() as tx_externa:

            @contextmanager
            def conexion_prueba():
                with conn.transaction():
                    yield conn

            monkeypatch.setattr(
                archivos_api, "connection", conexion_prueba
            )
            monkeypatch.setattr(
                jornadas_api, "connection", conexion_prueba
            )
            monkeypatch.setenv(
                "UPLOAD_DIR", str(tmp_path)
            )

            try:
                with TestClient(app) as cliente:
                    yield cliente, conn, tmp_path
            finally:
                tx_externa.force_rollback = True


def test_recepcion_ha22(entorno_archivos):
    fecha = fecha_prueba(30)
    cliente, conn, directorio = entorno_archivos

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO con_jornada (
                fecha_contable, estado
            )
            VALUES (%s, 'PENDIENTE')
            RETURNING id_jornada
        """, (fecha,))
        id_jornada = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO con_insumo_esperado (
                id_jornada,
                tipo_insumo,
                fuente,
                obligatorio,
                estado
            )
            VALUES (%s, 'HA22', 'HOST', TRUE, 'PENDIENTE')
        """, (id_jornada,))

    contenido = generar_ha22_valido(fecha)
    checksum = hashlib.sha256(contenido).hexdigest()

    respuesta = cliente.post(
        "/api/v1/archivos",
        data={
            "fecha_contable": fecha.isoformat(),
            "tipo_archivo": "HA22"
        },
        files={
            "archivo": (
                nombre_ha22(fecha),
                contenido,
                "text/plain"
            )
        }
    )

    assert respuesta.status_code == 201, respuesta.text

    datos = respuesta.json()
    assert datos["estado"] == "RECIBIDO"
    assert datos["checksum_sha256"] == checksum

    with conn.cursor() as cur:
        cur.execute("""
            SELECT estado, checksum_sha256
            FROM con_archivo_carga
            WHERE id_archivo = %s
        """, (datos["id_archivo"],))
        archivo = cur.fetchone()

        assert archivo[0] == "RECIBIDO"
        assert archivo[1].strip() == checksum

        cur.execute("""
            SELECT estado, id_archivo
            FROM con_insumo_esperado
            WHERE id_jornada = %s
              AND tipo_insumo = 'HA22'
        """, (id_jornada,))
        insumo = cur.fetchone()

        assert insumo == ("RECIBIDO", datos["id_archivo"])

        cur.execute("""
            SELECT COUNT(*)
            FROM con_trazabilidad
            WHERE id_archivo = %s
              AND tipo_evento = 'ARCHIVO_RECIBIDO'
        """, (datos["id_archivo"],))

        assert cur.fetchone()[0] == 1

    assert len(list(directorio.glob("*.bin"))) == 1


def test_rechazar_archivo_vacio(entorno_archivos):
    fecha = fecha_prueba(31)
    cliente, conn, directorio = entorno_archivos

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO con_jornada (
                fecha_contable, estado
            )
            VALUES (%s, 'PENDIENTE')
            RETURNING id_jornada
        """, (fecha,))
        id_jornada = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO con_insumo_esperado (
                id_jornada,
                tipo_insumo,
                fuente,
                obligatorio,
                estado
            )
            VALUES (%s, 'HA22', 'HOST', TRUE, 'PENDIENTE')
        """, (id_jornada,))

    respuesta = cliente.post(
        "/api/v1/archivos",
        data={
            "fecha_contable": fecha.isoformat(),
            "tipo_archivo": "HA22"
        },
        files={
            "archivo": (
                nombre_ha22(fecha),
                b"",
                "text/plain"
            )
        }
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == "Archivo vacio"

    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
            FROM con_insumo_esperado
            WHERE id_jornada = %s
              AND id_archivo IS NOT NULL
        """, (id_jornada,))
        assert cur.fetchone()[0] == 0

        cur.execute("""
            SELECT estado
            FROM con_insumo_esperado
            WHERE id_jornada = %s
        """, (id_jornada,))
        assert cur.fetchone()[0] == "PENDIENTE"

        cur.execute("""

            SELECT COUNT(*)
            FROM con_trazabilidad t
            JOIN con_archivo_carga a
              ON a.id_archivo = t.id_archivo
            JOIN con_insumo_esperado i
              ON i.id_archivo = a.id_archivo
            WHERE i.id_jornada = %s

        """, (id_jornada,))
        assert cur.fetchone()[0] == 0

    assert list(directorio.iterdir()) == []


def test_rechazar_checksum_duplicado(entorno_archivos):
    from psycopg import errors

    cliente, conn, directorio = entorno_archivos

    fecha = fecha_prueba(32)
    contenido = generar_ha22_valido(fecha)
    checksum = hashlib.sha256(contenido).hexdigest()

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO con_jornada (fecha_contable, estado)
            VALUES (%s, 'PENDIENTE')
            RETURNING id_jornada
        """, (fecha,))
        id_jornada = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO con_insumo_esperado (
                id_jornada, tipo_insumo, fuente,
                obligatorio, estado
            )
            VALUES (%s, 'HA22', 'HOST', TRUE, 'PENDIENTE')
        """, (id_jornada,))

    respuesta = cliente.post(
        "/api/v1/archivos",
        data={
            "fecha_contable": fecha.isoformat(),
            "tipo_archivo": "HA22",
        },
        files={
            "archivo": (
                nombre_ha22(fecha),
                contenido,
                "text/plain",
            )
        },
    )

    assert respuesta.status_code == 201, respuesta.text

    with pytest.raises(errors.UniqueViolation):
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO con_archivo_carga (
                        fecha_contable,
                        proceso_origen,
                        tipo_archivo,
                        nombre_archivo,
                        ruta_archivo,
                        checksum_sha256,
                        estado,
                        correlation_id
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, (
                    fecha,
                    "HOST",
                    "HA22",
                    nombre_ha22(fecha),
                    str(directorio / "duplicado.bin"),
                    checksum,
                    "RECIBIDO",
                    "checksum-test",
                ))

    print("CHECKSUM DUPLICADO RECHAZADO POR POSTGRESQL")



def test_rechazar_archivo_demasiado_grande(entorno_archivos):
    fecha = fecha_prueba(33)
    cliente, conn, directorio = entorno_archivos

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO con_jornada (fecha_contable, estado)
            VALUES (%s, 'PENDIENTE')
            RETURNING id_jornada
        """, (fecha,))
        id_jornada = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO con_insumo_esperado (
                id_jornada, tipo_insumo, fuente,
                obligatorio, estado
            )
            VALUES (%s, 'HA22', 'HOST', TRUE, 'PENDIENTE')
        """, (id_jornada,))

    contenido = b"A" * (20 * 1024 * 1024 + 1)

    respuesta = cliente.post(
        "/api/v1/archivos",
        data={
            "fecha_contable": fecha.isoformat(),
            "tipo_archivo": "HA22"
        },
        files={
            "archivo": (
                nombre_ha22(fecha),
                contenido,
                "text/plain"
            )
        }
    )

    assert respuesta.status_code == 413
    assert respuesta.json()["detail"] == (
        "Archivo supera el limite permitido"
    )

    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
            FROM con_insumo_esperado
            WHERE id_jornada = %s
              AND id_archivo IS NOT NULL
        """, (id_jornada,))
        assert cur.fetchone()[0] == 0

        cur.execute("""
            SELECT estado
            FROM con_insumo_esperado
            WHERE id_jornada = %s
        """, (id_jornada,))
        assert cur.fetchone()[0] == "PENDIENTE"

        cur.execute("""

            SELECT COUNT(*)
            FROM con_trazabilidad t
            JOIN con_archivo_carga a
              ON a.id_archivo = t.id_archivo
            JOIN con_insumo_esperado i
              ON i.id_archivo = a.id_archivo
            WHERE i.id_jornada = %s

        """, (id_jornada,))
        assert cur.fetchone()[0] == 0

    assert list(directorio.iterdir()) == []


def test_limpieza_archivo_si_falla_commit(monkeypatch, tmp_path):
    fecha = fecha_prueba(34)
    from contextlib import contextmanager
    from psycopg import OperationalError

    from app.api import archivos as api

    class CursorSimulado:
        def __init__(self):
            self.consultas = 0

        def execute(self, sql, params=None):
            self.consultas += 1

        def fetchone(self):
            if self.consultas == 1:
                return {
                    "id_jornada": 999,
                    "id_insumo_esperado": 999,
                    "estado": "PENDIENTE"
                }

            return {"id_archivo": 999}

    class ConexionSimulada:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            if exc_type is None:
                raise OperationalError(
                    "Fallo simulado durante COMMIT"
                )
            return False

        @contextmanager
        def cursor(self, row_factory=None):
            yield CursorSimulado()

    @contextmanager
    def conexion_fallida():
        with ConexionSimulada() as conn:
            yield conn

    monkeypatch.setattr(
        api, "connection", conexion_fallida
    )

    monkeypatch.setenv(
        "UPLOAD_DIR", str(tmp_path)
    )

    with TestClient(app) as cliente:
        respuesta = cliente.post(
            "/api/v1/archivos",
            data={
                "fecha_contable": fecha.isoformat(),
                "tipo_archivo": "HA22"
            },
            files={
                "archivo": (
                    nombre_ha22(fecha),
                    generar_ha22_valido(fecha),
                    "text/plain"
                )
            }
        )

    assert respuesta.status_code == 503
    assert respuesta.json()["detail"] == (
        "Base de datos no disponible"
    )

    assert list(tmp_path.iterdir()) == []
