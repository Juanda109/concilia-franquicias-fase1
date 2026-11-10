import hashlib
import os
from contextlib import contextmanager
from datetime import date, timedelta
from uuid import uuid4

import pytest

from fabricas_archivos import generar_ha22_valido
from fabricas_archivos import (
    generar_ha26_valido,
    generar_ha32_valido,
)

from app.repositories.database import connection as real_connection
from app.services import procesamiento_host


@pytest.fixture
def entorno_host(monkeypatch, tmp_path):
    if os.environ.get("DB_NAME") != "concilia_test":
        pytest.fail("Las pruebas requieren concilia_test")

    with real_connection() as conn:
        if conn.info.dbname != "concilia_test":
            pytest.fail("Base no autorizada")

        with conn.transaction() as transaccion:

            @contextmanager
            def conexion_prueba():
                with conn.transaction():
                    yield conn

            monkeypatch.setattr(
                procesamiento_host,
                "connection",
                conexion_prueba,
            )

            try:
                yield conn, tmp_path
            finally:
                transaccion.force_rollback = True


def fecha_disponible(conn):
    fecha = date.today() + timedelta(days=60)

    with conn.cursor() as cur:
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

    raise RuntimeError("No hay fechas disponibles")


def test_procesamiento_ha22_transaccional(entorno_host):
    conn, directorio = entorno_host
    fecha = fecha_disponible(conn)

    contenido = generar_ha22_valido(fecha)
    checksum = hashlib.sha256(contenido).hexdigest()
    correlacion = str(uuid4())

    ruta = directorio / f"DESCARHA22_F{fecha:%y%m%d}.TXT"
    ruta.write_bytes(contenido)

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
            INSERT INTO con_archivo_carga (
                fecha_contable,
                proceso_origen,
                tipo_archivo,
                nombre_archivo,
                ruta_archivo,
                checksum_sha256,
                total_registros,
                estado,
                correlation_id
            )
            VALUES (
                %s, 'HOST', 'HA22', %s, %s,
                %s, 1, 'RECIBIDO', %s
            )
            RETURNING id_archivo
        """, (
            fecha, ruta.name, str(ruta),
            checksum, correlacion,
        ))
        id_archivo = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO con_insumo_esperado (
                id_jornada,
                tipo_insumo,
                fuente,
                obligatorio,
                estado,
                id_archivo
            )
            VALUES (
                %s, 'HA22', 'HOST',
                TRUE, 'RECIBIDO', %s
            )
        """, (id_jornada, id_archivo))

    respuesta = procesamiento_host.procesar_host(id_archivo)

    assert respuesta["estado"] == "PROCESADO"
    assert respuesta["registros"] == 1
    assert respuesta["idempotente"] is False

    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                valor_debe,
                valor_haber,
                valor_normalizado,
                valor_saldo,
                linea_origen
            FROM con_host_resultado
            WHERE id_archivo = %s
        """, (id_archivo,))

        filas = cur.fetchall()

        assert len(filas) == 1
        assert filas[0][0] == 100
        assert filas[0][1] == 0
        assert filas[0][2] == 100
        assert filas[0][3] is None
        assert filas[0][4] == 2

        cur.execute("""
            SELECT estado
            FROM con_insumo_esperado
            WHERE id_archivo = %s
        """, (id_archivo,))
        assert cur.fetchone()[0] == "PROCESADO"

        cur.execute("""
            SELECT estado
            FROM con_archivo_carga
            WHERE id_archivo = %s
        """, (id_archivo,))
        assert cur.fetchone()[0] == "PROCESADO"

        cur.execute("""
            SELECT COUNT(*)
            FROM con_trazabilidad
            WHERE id_archivo = %s
              AND tipo_evento = 'ARCHIVO_PROCESADO'
        """, (id_archivo,))
        assert cur.fetchone()[0] == 1

    segundo = procesamiento_host.procesar_host(id_archivo)

    assert segundo["idempotente"] is True
    assert segundo["registros"] == 1

    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
            FROM con_host_resultado
            WHERE id_archivo = %s
        """, (id_archivo,))
        assert cur.fetchone()[0] == 1


@pytest.mark.parametrize(
    "tipo,fabrica,debe,haber,saldo",
    [
        ("HA26", generar_ha26_valido, 250, 50, None),
        ("HA32", generar_ha32_valido, 300, 100, 1500),
    ],
)
def test_procesamiento_ha26_ha32(
    entorno_host, tipo, fabrica, debe, haber, saldo
):
    conn, directorio = entorno_host
    fecha = fecha_disponible(conn)

    contenido = fabrica(fecha)
    checksum = hashlib.sha256(contenido).hexdigest()
    correlacion = str(uuid4())

    ruta = directorio / f"DESCAR{tipo}_F{fecha:%y%m%d}.TXT"
    ruta.write_bytes(contenido)

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO con_jornada (fecha_contable, estado)
            VALUES (%s, 'PENDIENTE')
            RETURNING id_jornada
        """, (fecha,))
        id_jornada = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO con_archivo_carga (
                fecha_contable,
                proceso_origen,
                tipo_archivo,
                nombre_archivo,
                ruta_archivo,
                checksum_sha256,
                total_registros,
                estado,
                correlation_id
            )
            VALUES (
                %s, 'HOST', %s, %s, %s,
                %s, 1, 'RECIBIDO', %s
            )
            RETURNING id_archivo
        """, (
            fecha, tipo, ruta.name, str(ruta),
            checksum, correlacion,
        ))
        id_archivo = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO con_insumo_esperado (
                id_jornada,
                tipo_insumo,
                fuente,
                obligatorio,
                estado,
                id_archivo
            )
            VALUES (
                %s, %s, 'HOST',
                TRUE, 'RECIBIDO', %s
            )
        """, (id_jornada, tipo, id_archivo))

    respuesta = procesamiento_host.procesar_host(id_archivo)

    assert respuesta["estado"] == "PROCESADO"
    assert respuesta["registros"] == 1
    assert respuesta["idempotente"] is False

    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                valor_debe,
                valor_haber,
                valor_normalizado,
                valor_saldo,
                linea_origen
            FROM con_host_resultado
            WHERE id_archivo = %s
        """, (id_archivo,))

        filas = cur.fetchall()

        assert len(filas) == 1

        valor_debe, valor_haber, neto, valor_saldo, linea = filas[0]

        assert valor_debe == debe
        assert valor_haber == haber
        assert neto == debe - haber
        assert valor_saldo == saldo
        assert linea == 2

        cur.execute("""
            SELECT estado
            FROM con_insumo_esperado
            WHERE id_archivo = %s
        """, (id_archivo,))
        assert cur.fetchone()[0] == "PROCESADO"

        cur.execute("""
            SELECT estado
            FROM con_archivo_carga
            WHERE id_archivo = %s
        """, (id_archivo,))
        assert cur.fetchone()[0] == "PROCESADO"

        cur.execute("""
            SELECT COUNT(*)
            FROM con_trazabilidad
            WHERE id_archivo = %s
              AND tipo_evento = 'ARCHIVO_PROCESADO'
        """, (id_archivo,))
        assert cur.fetchone()[0] == 1

    segundo = procesamiento_host.procesar_host(id_archivo)

    assert segundo["idempotente"] is True
    assert segundo["registros"] == 1

    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
            FROM con_host_resultado
            WHERE id_archivo = %s
        """, (id_archivo,))
        assert cur.fetchone()[0] == 1
