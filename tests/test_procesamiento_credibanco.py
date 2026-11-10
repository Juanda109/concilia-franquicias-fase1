"""Pruebas transaccionales CANT aisladas mediante rollback externo.

Se usan los identificadores reales solo en concilia_test. Los cambios temporales
se revierten siempre y el parser se sustituye por cuatro registros controlados.
"""
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import os

import pytest

from app.repositories.database import connection as real_connection
from app.services import procesamiento_credibanco
from app.services.normalizacion_credibanco import CUENTA_REPRESENTACION

ID_ARCHIVO = None
ID_JORNADA = None
VALORES = ("1850000", "132000", "56592", "169829")
LINEAS = (221, 222, 223, 224)


@pytest.fixture
def entorno_cant(monkeypatch, tmp_path):
    """Crea jornada y CANT temporales sin depender de IDs históricos."""
    import hashlib
    import uuid
    from datetime import date

    if os.environ.get("DB_NAME") != "concilia_test":
        pytest.fail("Solo se permite concilia_test")

    with real_connection() as conn:
        if conn.info.dbname != "concilia_test":
            pytest.fail("Conexion distinta de concilia_test")

        with conn.transaction() as transaccion:
            try:
                with conn.cursor() as cur:
                    # Fecha aislada dentro de la transacción; evita colisiones.
                    cur.execute("""SELECT d::date FROM generate_series(
                        DATE '2099-01-01', DATE '2099-12-31', INTERVAL '1 day'
                    ) d WHERE NOT EXISTS (
                        SELECT 1 FROM con_jornada j WHERE j.fecha_contable=d::date
                    ) LIMIT 1""")
                    fecha = cur.fetchone()[0]
                    cur.execute("""INSERT INTO con_jornada (fecha_contable,estado)
                                   VALUES (%s,'PENDIENTE') RETURNING id_jornada""", (fecha,))
                    jornada = cur.fetchone()[0]

                    ruta = tmp_path / "cant_controlado.txt"
                    ruta.write_bytes(b"CANT_PRUEBA_TRANSACCIONAL\n")
                    checksum = hashlib.sha256(ruta.read_bytes()).hexdigest()
                    correlacion = uuid.uuid4().hex
                    cur.execute("""INSERT INTO con_archivo_carga
                        (fecha_contable,proceso_origen,tipo_archivo,franquicia,
                         nombre_archivo,ruta_archivo,checksum_sha256,total_registros,
                         estado,correlation_id)
                        VALUES (%s,'CREDIBANCO','CANT','CREDIBANCO',%s,%s,%s,4,
                                'RECIBIDO',%s) RETURNING id_archivo""",
                        (fecha, ruta.name, str(ruta), checksum, correlacion))
                    archivo = cur.fetchone()[0]
                    cur.execute("""INSERT INTO con_insumo_esperado
                        (id_jornada,tipo_insumo,fuente,obligatorio,estado,id_archivo)
                        VALUES (%s,'CANT','CREDIBANCO',TRUE,'RECIBIDO',%s)""",
                        (jornada, archivo))

                monkeypatch.setitem(globals(), "ID_JORNADA", jornada)
                monkeypatch.setitem(globals(), "ID_ARCHIVO", archivo)

                @contextmanager
                def conexion_prueba():
                    with conn.transaction():
                        yield conn

                monkeypatch.setattr(
                    procesamiento_credibanco, "connection", conexion_prueba
                )
                registros = [
                    {"numero_linea": linea, "CUENTA": CUENTA_REPRESENTACION,
                     "VL_TOTAL": valor, "TX": "36", "BIN_DEST": "492489"}
                    for linea, valor in zip(LINEAS, VALORES)
                ]
                parser = SimpleNamespace(
                    parse=lambda ruta: SimpleNamespace(records=registros, errors=[])
                )
                monkeypatch.setattr(
                    procesamiento_credibanco, "obtener_parser",
                    lambda tipo: parser if tipo == "CANT" else None
                )
                yield conn
            finally:
                transaccion.force_rollback = True



def test_procesamiento_cant_real(entorno_cant):
    conn = entorno_cant
    primero = procesamiento_credibanco.procesar_cant(ID_ARCHIVO)
    assert primero == {
        "id_archivo": ID_ARCHIVO,
        "estado": "PROCESADO",
        "registros": 4,
        "idempotente": False,
    }

    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*), SUM(valor), COUNT(DISTINCT linea_origen)
            FROM con_franquicia_resultado WHERE id_archivo = %s
        """, (ID_ARCHIVO,))
        assert cur.fetchone() == (4, Decimal("2208421"), 4)
        cur.execute("""
            SELECT a.estado, i.estado FROM con_archivo_carga a
            JOIN con_insumo_esperado i ON i.id_archivo = a.id_archivo
            WHERE a.id_archivo = %s AND i.id_jornada = %s
        """, (ID_ARCHIVO, ID_JORNADA))
        assert cur.fetchone() == ("PROCESADO", "PROCESADO")
        cur.execute("""
            SELECT COUNT(*) FROM con_trazabilidad
            WHERE id_archivo = %s AND tipo_evento = 'ARCHIVO_PROCESADO'
              AND componente = 'PROCESAMIENTO_CREDIBANCO'
        """, (ID_ARCHIVO,))
        assert cur.fetchone()[0] == 1

    segundo = procesamiento_credibanco.procesar_cant(ID_ARCHIVO)
    assert segundo["idempotente"] is True
    assert segundo["registros"] == 4
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM con_franquicia_resultado
            WHERE id_archivo = %s
        """, (ID_ARCHIVO,))
        assert cur.fetchone()[0] == 4


def test_rollback_segunda_insercion_cant(entorno_cant, monkeypatch):
    conn = entorno_cant

    class CursorConFallo:
        def __init__(self, cursor, estado):
            self.cursor_real = cursor
            self.estado = estado

        def execute(self, consulta, parametros=None):
            if "INSERT INTO con_franquicia_resultado" in consulta:
                self.estado["inserciones"] += 1
                if self.estado["inserciones"] == 2:
                    raise RuntimeError("FALLO_SIMULADO_SEGUNDA_INSERCION_CANT")
            return self.cursor_real.execute(consulta, parametros)

        def __getattr__(self, nombre):
            return getattr(self.cursor_real, nombre)

    class ConexionConFallo:
        def __init__(self, conexion, estado):
            self.conexion = conexion
            self.estado = estado

        @contextmanager
        def cursor(self):
            with self.conexion.cursor() as cursor:
                yield CursorConFallo(cursor, self.estado)

    estado = {"inserciones": 0}

    @contextmanager
    def conexion_con_fallo():
        with conn.transaction():
            yield ConexionConFallo(conn, estado)

    monkeypatch.setattr(
        procesamiento_credibanco, "connection", conexion_con_fallo
    )

    with pytest.raises(
        RuntimeError, match="FALLO_SIMULADO_SEGUNDA_INSERCION_CANT"
    ):
        procesamiento_credibanco.procesar_cant(ID_ARCHIVO)
    assert estado["inserciones"] == 2

    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM con_franquicia_resultado
            WHERE id_archivo = %s
        """, (ID_ARCHIVO,))
        assert cur.fetchone()[0] == 0
        cur.execute("""
            SELECT a.estado, i.estado FROM con_archivo_carga a
            JOIN con_insumo_esperado i ON i.id_archivo = a.id_archivo
            WHERE a.id_archivo = %s AND i.id_jornada = %s
        """, (ID_ARCHIVO, ID_JORNADA))
        assert cur.fetchone() == ("RECIBIDO", "RECIBIDO")
        cur.execute("""
            SELECT COUNT(*) FROM con_trazabilidad
            WHERE id_archivo = %s AND tipo_evento = 'ARCHIVO_PROCESADO'
              AND componente = 'PROCESAMIENTO_CREDIBANCO'
        """, (ID_ARCHIVO,))
        assert cur.fetchone()[0] == 0
