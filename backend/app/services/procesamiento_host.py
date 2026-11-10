from app.services.bloqueo_jornada import verificar_jornada_modificable
from app.services.bloqueo_jornada import verificar_asociacion_jornada
from app.services.bloqueo_jornada import bloquear_jornada_por_archivo
"""Procesamiento transaccional de archivos Host."""

from pathlib import Path
import hashlib

from app.repositories.database import connection
from app.ingestion.registry import obtener_parser
from app.services.validacion_fechas_host import validar_fechas_host
from app.services.normalizacion_host import normalizar_host


TIPOS_HOST = frozenset(("HA22", "HA26", "HA32"))


class ProcesamientoHostError(ValueError):
    pass


def procesar_host(id_archivo):
    """Procesa un archivo Host previamente recibido."""

    with connection() as conn:
        with conn.cursor() as cur:

            cur.execute("SELECT current_database()")
            base = cur.fetchone()[0]

            id_jornada_bloqueada = bloquear_jornada_por_archivo(
                cur, id_archivo
            )

            verificar_asociacion_jornada(
                cur, id_archivo, id_jornada_bloqueada
            )

            verificar_jornada_modificable(
                cur, id_jornada_bloqueada
            )

            cur.execute("""
                SELECT
                    a.id_archivo,
                    a.tipo_archivo,
                    a.checksum_sha256,
                    a.total_registros,
                    i.tipo_insumo,
                    a.ruta_archivo,
                    a.fecha_contable,
                    a.correlation_id,
                    a.estado AS estado_archivo,
                    i.id_insumo_esperado,
                    i.id_jornada,
                    i.estado AS estado_insumo,
                    j.fecha_contable AS fecha_jornada
                FROM con_archivo_carga a
                JOIN con_insumo_esperado i
                  ON i.id_archivo = a.id_archivo
                JOIN con_jornada j
                  ON j.id_jornada = i.id_jornada
                WHERE a.id_archivo = %s
                FOR UPDATE OF a, i
            """, (id_archivo,))

            columnas = [c.name for c in cur.description]
            fila = cur.fetchone()

            if fila is None:
                raise ProcesamientoHostError(
                    "Archivo no asociado a una jornada"
                )

            datos = dict(zip(columnas, fila))

            tipo = datos["tipo_archivo"]

            if tipo not in TIPOS_HOST:
                raise ProcesamientoHostError(
                    "El archivo no pertenece a Host"
                )

            if datos["tipo_insumo"] != tipo:
                raise ProcesamientoHostError(
                    "Tipo de archivo distinto al insumo esperado"
                )

            if datos["fecha_contable"] != datos["fecha_jornada"]:
                raise ProcesamientoHostError(
                    "Fecha del archivo distinta a la jornada"
                )

            if datos["estado_insumo"] == "PROCESADO":
                if datos["estado_archivo"] != "PROCESADO":
                    raise ProcesamientoHostError(
                        "Estado de archivo inconsistente"
                    )

                cur.execute("""
                    SELECT COUNT(*)
                    FROM con_host_resultado
                    WHERE id_archivo = %s
                """, (id_archivo,))

                total = cur.fetchone()[0]

                if total <= 0:
                    raise ProcesamientoHostError(
                        "Archivo procesado sin resultados Host"
                    )

                esperado = datos["total_registros"]

                if esperado is None or total != esperado:
                    raise ProcesamientoHostError(
                        "Cantidad persistida distinta al total del archivo"
                    )

                cur.execute("""
                    SELECT COUNT(*)
                    FROM con_trazabilidad
                    WHERE id_archivo = %s
                      AND tipo_evento = 'ARCHIVO_PROCESADO'
                      AND componente = 'PROCESAMIENTO_HOST'
                """, (id_archivo,))

                if cur.fetchone()[0] != 1:
                    raise ProcesamientoHostError(
                        "Trazabilidad de procesamiento inconsistente"
                    )

                return {
                    "id_archivo": id_archivo,
                    "tipo_archivo": tipo,
                    "estado": "PROCESADO",
                    "registros": total,
                    "idempotente": True,
                }

            if (
                datos["estado_insumo"] != "RECIBIDO"
                or datos["estado_archivo"] != "RECIBIDO"
            ):
                raise ProcesamientoHostError(
                    "Archivo no disponible para procesamiento"
                )

            ruta = Path(datos["ruta_archivo"])

            if not ruta.is_file():
                raise ProcesamientoHostError(
                    "Archivo fisico no encontrado"
                )

            checksum = hashlib.sha256()

            with ruta.open("rb") as archivo:
                for bloque in iter(
                    lambda: archivo.read(1024 * 1024),
                    b"",
                ):
                    checksum.update(bloque)

            if checksum.hexdigest() != datos["checksum_sha256"].strip():
                raise ProcesamientoHostError(
                    "Checksum del archivo fisico no corresponde"
                )

            cur.execute("""
                SELECT COUNT(*)
                FROM con_host_resultado
                WHERE id_archivo = %s
            """, (id_archivo,))

            if cur.fetchone()[0] != 0:
                raise ProcesamientoHostError(
                    "Existen resultados previos inconsistentes"
                )

            resultado = obtener_parser(tipo).parse(ruta)

            if resultado.errors:
                raise ProcesamientoHostError(
                    f"Parser reporto {len(resultado.errors)} errores"
                )

            validar_fechas_host(
                tipo_insumo=tipo,
                fecha_contable=datos["fecha_jornada"],
                resultado=resultado,
            )

            filas = normalizar_host(
                tipo=tipo,
                registros=resultado.records,
                fecha_contable=datos["fecha_jornada"],
                id_archivo=id_archivo,
                correlation_id=datos["correlation_id"],
            )

            if not filas:
                raise ProcesamientoHostError(
                    "Archivo Host sin registros persistibles"
                )

            for registro in filas:
                cur.execute("""
                    INSERT INTO con_host_resultado (
                        id_archivo,
                        fecha_contable,
                        tx_host,
                        cuenta,
                        centro,
                        referencia,
                        concepto,
                        valor_debe,
                        valor_haber,
                        valor_saldo,
                        valor_normalizado,
                        linea_origen,
                        correlation_id
                    )
                    VALUES (
                        %(id_archivo)s,
                        %(fecha_contable)s,
                        %(tx_host)s,
                        %(cuenta)s,
                        %(centro)s,
                        %(referencia)s,
                        %(concepto)s,
                        %(valor_debe)s,
                        %(valor_haber)s,
                        %(valor_saldo)s,
                        %(valor_normalizado)s,
                        %(linea_origen)s,
                        %(correlation_id)s
                    )
                """, registro)

            cur.execute("""
                UPDATE con_insumo_esperado
                SET estado = 'PROCESADO',
                    fec_actualizacion = CURRENT_TIMESTAMP
                WHERE id_insumo_esperado = %s
                  AND estado = 'RECIBIDO'
            """, (datos["id_insumo_esperado"],))

            if cur.rowcount != 1:
                raise ProcesamientoHostError(
                    "No se pudo actualizar el insumo"
                )

            cur.execute("""
                UPDATE con_archivo_carga
                SET estado = 'PROCESADO'
                WHERE id_archivo = %s
                  AND estado = 'RECIBIDO'
            """, (id_archivo,))

            if cur.rowcount != 1:
                raise ProcesamientoHostError(
                    "No se pudo actualizar el archivo"
                )

            cur.execute("""
                INSERT INTO con_trazabilidad (
                    correlation_id,
                    id_archivo,
                    tipo_evento,
                    componente,
                    detalle
                )
                VALUES (%s, %s, %s, %s, %s)
            """, (
                datos["correlation_id"],
                id_archivo,
                "ARCHIVO_PROCESADO",
                "PROCESAMIENTO_HOST",
                f"Procesados {len(filas)} registros {tipo}",
            ))

            return {
                "id_archivo": id_archivo,
                "tipo_archivo": tipo,
                "estado": "PROCESADO",
                "registros": len(filas),
                "idempotente": False,
            }
