import hashlib
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from fabricas_archivos import generar_ha22_valido
from test_procesamiento_host import entorno_host, fecha_disponible


def test_http_host_postgresql(entorno_host):
    conn, directorio = entorno_host
    fecha = fecha_disponible(conn)

    contenido = generar_ha22_valido(fecha)
    checksum = hashlib.sha256(contenido).hexdigest()
    correlacion = str(uuid4())

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
            checksum,
            correlacion,
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

    with TestClient(app) as cliente:
        respuesta = cliente.post(
            f"/api/v1/archivos/{archivo}/procesar"
        )

        assert respuesta.status_code == 200, respuesta.text

        datos = respuesta.json()

        assert datos["estado"] == "PROCESADO"
        assert datos["registros"] == 1
        assert datos["idempotente"] is False

        segundo = cliente.post(
            f"/api/v1/archivos/{archivo}/procesar"
        )

        assert segundo.status_code == 200
        assert segundo.json()["idempotente"] is True

    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
            FROM con_host_resultado
            WHERE id_archivo = %s
        """, (archivo,))

        assert cur.fetchone()[0] == 1

        cur.execute("""
            SELECT estado
            FROM con_archivo_carga
            WHERE id_archivo = %s
        """, (archivo,))

        assert cur.fetchone()[0] == "PROCESADO"

        cur.execute("""
            SELECT estado
            FROM con_insumo_esperado
            WHERE id_archivo = %s
        """, (archivo,))

        assert cur.fetchone()[0] == "PROCESADO"

        cur.execute("""
            SELECT COUNT(*)
            FROM con_trazabilidad
            WHERE id_archivo = %s
              AND tipo_evento = 'ARCHIVO_PROCESADO'
        """, (archivo,))

        assert cur.fetchone()[0] == 1
