import hashlib
from uuid import uuid4

import pytest

from fabricas_archivos import generar_ha22_valido
from test_procesamiento_host import entorno_host, fecha_disponible
from app.services import procesamiento_host


def preparar_archivo(conn, directorio, fecha, contenido):
    ruta = directorio / f"DESCARHA22_F{fecha:%y%m%d}.TXT"
    ruta.write_bytes(contenido)

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO con_jornada (fecha_contable, estado)
            VALUES (%s, 'PENDIENTE')
            RETURNING id_jornada
        """, (fecha,))
        jornada = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO con_archivo_carga (
                fecha_contable, proceso_origen,
                tipo_archivo, nombre_archivo,
                ruta_archivo, checksum_sha256,
                total_registros, estado, correlation_id
            )
            VALUES (
                %s, 'HOST', 'HA22', %s, %s,
                %s, 1, 'RECIBIDO', %s
            )
            RETURNING id_archivo
        """, (
            fecha,
            ruta.name,
            str(ruta),
            hashlib.sha256(contenido).hexdigest(),
            str(uuid4()),
        ))
        archivo = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO con_insumo_esperado (
                id_jornada, tipo_insumo, fuente,
                obligatorio, estado, id_archivo
            )
            VALUES (
                %s, 'HA22', 'HOST',
                TRUE, 'RECIBIDO', %s
            )
        """, (jornada, archivo))

    return archivo, ruta


def verificar_sin_procesamiento(conn, archivo):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
            FROM con_host_resultado
            WHERE id_archivo = %s
        """, (archivo,))
        assert cur.fetchone()[0] == 0

        cur.execute("""
            SELECT estado
            FROM con_archivo_carga
            WHERE id_archivo = %s
        """, (archivo,))
        assert cur.fetchone()[0] == "RECIBIDO"

        cur.execute("""
            SELECT estado
            FROM con_insumo_esperado
            WHERE id_archivo = %s
        """, (archivo,))
        assert cur.fetchone()[0] == "RECIBIDO"

        cur.execute("""
            SELECT COUNT(*)
            FROM con_trazabilidad
            WHERE id_archivo = %s
              AND tipo_evento = 'ARCHIVO_PROCESADO'
        """, (archivo,))
        assert cur.fetchone()[0] == 0


def test_rechaza_checksum_alterado(entorno_host):
    conn, directorio = entorno_host
    fecha = fecha_disponible(conn)
    contenido = generar_ha22_valido(fecha)

    archivo, ruta = preparar_archivo(
        conn, directorio, fecha, contenido
    )

    ruta.write_bytes(contenido + b"ALTERADO")

    with pytest.raises(
        procesamiento_host.ProcesamientoHostError,
        match="Checksum",
    ):
        procesamiento_host.procesar_host(archivo)

    verificar_sin_procesamiento(conn, archivo)


def test_rechaza_fecha_interna_incorrecta(entorno_host):
    from datetime import timedelta
    from app.services.validacion_fechas_host import (
        FechaInternaHostInvalida,
    )

    conn, directorio = entorno_host
    fecha = fecha_disponible(conn)
    contenido = generar_ha22_valido(
        fecha - timedelta(days=1)
    )

    archivo, ruta = preparar_archivo(
        conn, directorio, fecha, contenido
    )

    with pytest.raises(FechaInternaHostInvalida):
        procesamiento_host.procesar_host(archivo)

    verificar_sin_procesamiento(conn, archivo)


def test_rechaza_identidad_incorrecta(entorno_host):
    conn, directorio = entorno_host
    fecha = fecha_disponible(conn)
    contenido = generar_ha22_valido(fecha)

    archivo, ruta = preparar_archivo(
        conn, directorio, fecha, contenido
    )

    with conn.cursor() as cur:
        cur.execute("""
            UPDATE con_insumo_esperado
            SET tipo_insumo = 'HA26'
            WHERE id_archivo = %s
        """, (archivo,))

    with pytest.raises(
        procesamiento_host.ProcesamientoHostError,
        match="Tipo de archivo distinto",
    ):
        procesamiento_host.procesar_host(archivo)

    verificar_sin_procesamiento(conn, archivo)


def test_rollback_segunda_insercion(entorno_host, monkeypatch):
    from contextlib import contextmanager
    from app.ingestion.registry import obtener_parser

    conn, directorio = entorno_host
    fecha = fecha_disponible(conn)

    contenido = generar_ha22_valido(fecha)

    # Duplicar movimiento, conservando dos lineas fisicas.
    lineas = contenido.splitlines(keepends=True)
    contenido = b"".join([
        lineas[0],
        lineas[1],
        lineas[1],
    ])

    archivo, ruta = preparar_archivo(
        conn, directorio, fecha, contenido
    )

    with conn.cursor() as cur:
        cur.execute("""
            UPDATE con_archivo_carga
            SET total_registros = 2,
                checksum_sha256 = %s
            WHERE id_archivo = %s
        """, (
            hashlib.sha256(contenido).hexdigest(),
            archivo,
        ))

    class CursorConFallo:
        def __init__(self, cursor):
            self.cursor = cursor
            self.inserciones = 0

        def execute(self, consulta, parametros=None):
            if "INSERT INTO con_host_resultado" in consulta:
                self.inserciones += 1

                if self.inserciones == 2:
                    raise RuntimeError(
                        "FALLO_SIMULADO_SEGUNDA_INSERCION"
                    )

            return self.cursor.execute(
                consulta, parametros
            )

        def __getattr__(self, nombre):
            return getattr(self.cursor, nombre)

        def __enter__(self):
            self.cursor.__enter__()
            return self

        def __exit__(self, tipo, valor, traza):
            return self.cursor.__exit__(tipo, valor, traza)

    class ConexionConFallo:
        def __init__(self, conexion):
            self.conexion = conexion
            self.inserciones = 0

        @contextmanager
        def cursor(self):
            with self.conexion.cursor() as real:
                envoltorio = CursorConFallo(real)
                yield envoltorio

        def __getattr__(self, nombre):
            return getattr(self.conexion, nombre)

    @contextmanager
    def conexion_prueba_fallo():
        with conn.transaction():
            yield ConexionConFallo(conn)

    monkeypatch.setattr(
        procesamiento_host,
        "connection",
        conexion_prueba_fallo,
    )

    with pytest.raises(
        RuntimeError,
        match="FALLO_SIMULADO_SEGUNDA_INSERCION",
    ):
        procesamiento_host.procesar_host(archivo)

    verificar_sin_procesamiento(conn, archivo)


@pytest.mark.parametrize(
    "escenario",
    [
        "ARCHIVO_PROCESADO_INSUMO_RECIBIDO",
        "INSUMO_PROCESADO_ARCHIVO_RECIBIDO",
        "TOTAL_REGISTROS_INCORRECTO",
        "TRAZABILIDAD_AUSENTE",
    ],
)
def test_inconsistencia_idempotencia(entorno_host, escenario):
    conn, directorio = entorno_host
    fecha = fecha_disponible(conn)
    contenido = generar_ha22_valido(fecha)

    archivo, ruta = preparar_archivo(
        conn, directorio, fecha, contenido
    )

    primero = procesamiento_host.procesar_host(archivo)

    assert primero["estado"] == "PROCESADO"
    assert primero["idempotente"] is False

    with conn.cursor() as cur:
        if escenario == "ARCHIVO_PROCESADO_INSUMO_RECIBIDO":
            cur.execute("""
                UPDATE con_insumo_esperado
                SET estado = 'RECIBIDO'
                WHERE id_archivo = %s
            """, (archivo,))

        elif escenario == "INSUMO_PROCESADO_ARCHIVO_RECIBIDO":
            cur.execute("""
                UPDATE con_archivo_carga
                SET estado = 'RECIBIDO'
                WHERE id_archivo = %s
            """, (archivo,))

        elif escenario == "TOTAL_REGISTROS_INCORRECTO":
            cur.execute("""
                UPDATE con_archivo_carga
                SET total_registros = 2
                WHERE id_archivo = %s
            """, (archivo,))

        elif escenario == "TRAZABILIDAD_AUSENTE":
            cur.execute("""
                DELETE FROM con_trazabilidad
                WHERE id_archivo = %s
                  AND tipo_evento = 'ARCHIVO_PROCESADO'
                  AND componente = 'PROCESAMIENTO_HOST'
            """, (archivo,))

    with pytest.raises(
        procesamiento_host.ProcesamientoHostError
    ):
        procesamiento_host.procesar_host(archivo)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
            FROM con_host_resultado
            WHERE id_archivo = %s
        """, (archivo,))

        assert cur.fetchone()[0] == 1
