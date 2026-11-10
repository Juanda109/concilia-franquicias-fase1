import hashlib
from uuid import uuid4

from fabricas_archivos import (
    generar_ha22_valido,
    generar_ha26_valido,
    generar_ha32_valido,
)
from test_procesamiento_host import entorno_host, fecha_disponible

from app.batch import host_loader
from app.services import procesamiento_host


def test_host_loader_postgresql(entorno_host, monkeypatch):
    from contextlib import contextmanager

    conn, directorio = entorno_host
    fecha = fecha_disponible(conn)

    fabricas = {
        "HA22": generar_ha22_valido,
        "HA26": generar_ha26_valido,
        "HA32": generar_ha32_valido,
    }

    ids = []

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO con_jornada (fecha_contable, estado)
            VALUES (%s, 'PENDIENTE')
            RETURNING id_jornada
        """, (fecha,))
        jornada = cur.fetchone()[0]

        for tipo, fabrica in fabricas.items():
            contenido = fabrica(fecha)

            ruta = (
                directorio
                / f"DESCAR{tipo}_F{fecha:%y%m%d}.TXT"
            )
            ruta.write_bytes(contenido)

            cur.execute("""
                INSERT INTO con_archivo_carga (
                    fecha_contable, proceso_origen,
                    tipo_archivo, nombre_archivo,
                    ruta_archivo, checksum_sha256,
                    total_registros, estado, correlation_id
                )
                VALUES (
                    %s, 'HOST', %s, %s, %s,
                    %s, 1, 'RECIBIDO', %s
                )
                RETURNING id_archivo
            """, (
                fecha,
                tipo,
                ruta.name,
                str(ruta),
                hashlib.sha256(contenido).hexdigest(),
                str(uuid4()),
            ))

            archivo = cur.fetchone()[0]
            ids.append(archivo)

            cur.execute("""
                INSERT INTO con_insumo_esperado (
                    id_jornada, tipo_insumo, fuente,
                    obligatorio, estado, id_archivo
                )
                VALUES (
                    %s, %s, 'HOST',
                    TRUE, 'RECIBIDO', %s
                )
            """, (jornada, tipo, archivo))

    @contextmanager
    def conexion_prueba():
        with conn.transaction():
            yield conn

    monkeypatch.setattr(
        host_loader,
        "connection",
        conexion_prueba,
    )

    # Aislar la seleccion para que solo incluya la jornada sintetica.
    consulta_original = host_loader.consultar_pendientes

    def consultar_solo_prueba(limite=100):
        pendientes = consulta_original(limite=1000)
        return [
            archivo for archivo in pendientes
            if archivo["id_archivo"] in ids
        ][:limite]

    monkeypatch.setattr(
        host_loader,
        "consultar_pendientes",
        consultar_solo_prueba,
    )

    resultado = host_loader.ejecutar_host_loader(
        limite=100,
        ejecutar=True,
    )

    assert resultado["total_pendientes"] == 3
    assert resultado["procesados"] == 3
    assert resultado["fallidos"] == 0

    with conn.cursor() as cur:
        for archivo in ids:
            cur.execute("""
                SELECT COUNT(*)
                FROM con_host_resultado
                WHERE id_archivo = %s
            """, (archivo,))
            assert cur.fetchone()[0] == 1

            cur.execute("""
                SELECT estado
                FROM con_insumo_esperado
                WHERE id_archivo = %s
            """, (archivo,))
            assert cur.fetchone()[0] == "PROCESADO"

            cur.execute("""
                SELECT estado
                FROM con_archivo_carga
                WHERE id_archivo = %s
            """, (archivo,))
            assert cur.fetchone()[0] == "PROCESADO"
