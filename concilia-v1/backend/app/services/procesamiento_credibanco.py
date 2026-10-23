from app.services.bloqueo_jornada import verificar_jornada_modificable
from app.services.bloqueo_jornada import verificar_asociacion_jornada
from app.services.bloqueo_jornada import bloquear_jornada_por_archivo
"""Procesamiento transaccional Credibanco CANT Fase 1."""

import hashlib
from pathlib import Path

from app.repositories.database import connection
from app.ingestion.registry import obtener_parser
from app.services.normalizacion_credibanco import normalizar_cant, CUENTA_REPRESENTACION


class ProcesamientoCredibancoError(ValueError):
    pass


def procesar_cant(id_archivo):
    """Procesa un archivo CANT recibido."""

    with connection() as conn:
        with conn.cursor() as cur:
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
                    a.ruta_archivo,
                    a.fecha_contable,
                    a.checksum_sha256,
                    a.total_registros,
                    a.correlation_id,
                    a.estado AS estado_archivo,
                    i.id_insumo_esperado,
                    i.tipo_insumo,
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
                raise ProcesamientoCredibancoError(
                    "Archivo CANT no asociado"
                )

            datos = dict(zip(columnas, fila))

            if (
                datos["tipo_archivo"] != "CANT"
                or datos["tipo_insumo"] != "CANT"
            ):
                raise ProcesamientoCredibancoError(
                    "Identidad CANT incorrecta"
                )

            if datos["fecha_contable"] != datos["fecha_jornada"]:
                raise ProcesamientoCredibancoError(
                    "Fecha CANT incompatible"
                )

            cur.execute("""
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT linea_origen)
                FROM con_franquicia_resultado
                WHERE id_archivo = %s
            """, (id_archivo,))

            total, lineas = cur.fetchone()

            if datos["estado_insumo"] == "PROCESADO":
                if datos["estado_archivo"] != "PROCESADO":
                    raise ProcesamientoCredibancoError(
                        "Estados CANT inconsistentes"
                    )

                if (
                    total <= 0
                    or total != datos["total_registros"]
                    or lineas != total
                ):
                    raise ProcesamientoCredibancoError(
                        "Resultados CANT inconsistentes"
                    )

                cur.execute("""
                    SELECT COUNT(*)
                    FROM con_trazabilidad
                    WHERE id_archivo = %s
                      AND tipo_evento = 'ARCHIVO_PROCESADO'
                      AND componente = 'PROCESAMIENTO_CREDIBANCO'
                """, (id_archivo,))

                if cur.fetchone()[0] != 1:
                    raise ProcesamientoCredibancoError(
                        "Trazabilidad CANT inconsistente"
                    )

                return {
                    "id_archivo": id_archivo,
                    "estado": "PROCESADO",
                    "registros": total,
                    "idempotente": True,
                }

            if (
                datos["estado_insumo"] != "RECIBIDO"
                or datos["estado_archivo"] != "RECIBIDO"
            ):
                raise ProcesamientoCredibancoError(
                    "CANT no disponible para procesamiento"
                )

            # Los resultados parciales se verifican en la rama de excepciones.
            if total != 0:
                cur.execute("SELECT COUNT(*) FROM con_cant_excepcion_cuenta WHERE id_archivo=%s", (id_archivo,))
                if cur.fetchone()[0] == 0:
                    raise ProcesamientoCredibancoError("Existen resultados CANT previos")

            ruta = Path(datos["ruta_archivo"])

            if not ruta.is_file():
                raise ProcesamientoCredibancoError(
                    "Archivo CANT fisico no encontrado"
                )

            checksum = hashlib.sha256()

            with ruta.open("rb") as archivo:
                for bloque in iter(
                    lambda: archivo.read(1024 * 1024),
                    b"",
                ):
                    checksum.update(bloque)

            if checksum.hexdigest() != datos["checksum_sha256"].strip():
                raise ProcesamientoCredibancoError(
                    "Checksum CANT incorrecto"
                )

            resultado = obtener_parser("CANT").parse(ruta)

            if resultado.errors:
                raise ProcesamientoCredibancoError(
                    "Parser CANT reporto errores"
                )

            # Cuentas sin regla aprobada: no se normalizan ni se descartan.
            # Se registran como excepciones funcionales de forma idempotente.
            sin_regla = [r for r in resultado.records
                         if r.get("CUENTA", "") != CUENTA_REPRESENTACION]
            aprobados = [r for r in resultado.records
                         if r.get("CUENTA", "") == CUENTA_REPRESENTACION]
            if sin_regla:
                # Validar lineas antes de cualquier escritura.
                lineas_origen = [r.get("numero_linea") for r in resultado.records]
                if (any(not isinstance(n, int) or n <= 0 for n in lineas_origen)
                        or len(lineas_origen) != len(set(lineas_origen))):
                    raise ProcesamientoCredibancoError("Lineas CANT invalidas o duplicadas")
                filas_aprobadas = normalizar_cant(
                    registros=aprobados,
                    fecha_contable=datos["fecha_jornada"],
                    id_archivo=id_archivo,
                    correlation_id=datos["correlation_id"],
                )
                # Reintento seguro: no duplicar normalizaciones ya persistidas.
                cur.execute("SELECT COUNT(*) FROM con_franquicia_resultado WHERE id_archivo=%s", (id_archivo,))
                existentes_norm = cur.fetchone()[0]
                if existentes_norm not in (0, len(filas_aprobadas)):
                    raise ProcesamientoCredibancoError("Normalizacion CANT parcial inconsistente")
                if existentes_norm == 0:
                    for registro in filas_aprobadas:
                        cur.execute("""INSERT INTO con_franquicia_resultado
                            (id_archivo,fecha_contable,proceso_origen,reporte_origen,
                             franquicia,cuenta,concepto,referencia,moneda,valor,
                             linea_origen,correlation_id)
                            VALUES (%(id_archivo)s,%(fecha_contable)s,
                                    %(proceso_origen)s,%(reporte_origen)s,
                                    %(franquicia)s,%(cuenta)s,%(concepto)s,
                                    %(referencia)s,%(moneda)s,%(valor)s,
                                    %(linea_origen)s,%(correlation_id)s)""", registro)
                for registro in sin_regla:
                    cur.execute("""INSERT INTO con_cant_excepcion_cuenta
                        (id_archivo,id_jornada,linea_origen,cuenta,correlation_id)
                        VALUES (%s,%s,%s,%s,%s)
                        ON CONFLICT (id_archivo,linea_origen) DO NOTHING""",
                        (id_archivo,id_jornada_bloqueada,registro["numero_linea"],
                         str(registro.get("CUENTA", "")),datos["correlation_id"]))
                cur.execute("""INSERT INTO con_trazabilidad
                    (correlation_id,id_archivo,id_jornada,tipo_evento,componente,detalle)
                    SELECT %s,%s,%s,'CANT_NORMALIZACION_PARCIAL',
                           'PROCESAMIENTO_CREDIBANCO',%s
                    WHERE NOT EXISTS (
                      SELECT 1 FROM con_trazabilidad
                      WHERE id_archivo=%s AND tipo_evento='CANT_NORMALIZACION_PARCIAL'
                    )""", (datos["correlation_id"],id_archivo,id_jornada_bloqueada,
                            f"{len(filas_aprobadas)} aprobados; {len(sin_regla)} sin regla",
                            id_archivo))
                return {"id_archivo": id_archivo, "estado": "REVISION_FUNCIONAL",
                        "registros_normalizados": len(filas_aprobadas),
                        "registros_sin_regla": len(sin_regla),
                        "idempotente": existentes_norm != 0}

            filas = normalizar_cant(
                registros=resultado.records,
                fecha_contable=datos["fecha_jornada"],
                id_archivo=id_archivo,
                correlation_id=datos["correlation_id"],
            )

            if (
                not filas
                or datos["total_registros"] != len(filas)
            ):
                raise ProcesamientoCredibancoError(
                    "Cantidad CANT incompatible"
                )

            for registro in filas:
                cur.execute("""
                    INSERT INTO con_franquicia_resultado (
                        id_archivo,
                        fecha_contable,
                        proceso_origen,
                        reporte_origen,
                        franquicia,
                        cuenta,
                        concepto,
                        referencia,
                        moneda,
                        valor,
                        linea_origen,
                        correlation_id
                    )
                    VALUES (
                        %(id_archivo)s,
                        %(fecha_contable)s,
                        %(proceso_origen)s,
                        %(reporte_origen)s,
                        %(franquicia)s,
                        %(cuenta)s,
                        %(concepto)s,
                        %(referencia)s,
                        %(moneda)s,
                        %(valor)s,
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
                raise ProcesamientoCredibancoError(
                    "No se actualizo insumo CANT"
                )

            cur.execute("""
                UPDATE con_archivo_carga
                SET estado = 'PROCESADO'
                WHERE id_archivo = %s
                  AND estado = 'RECIBIDO'
            """, (id_archivo,))

            if cur.rowcount != 1:
                raise ProcesamientoCredibancoError(
                    "No se actualizo archivo CANT"
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
                "PROCESAMIENTO_CREDIBANCO",
                f"CANT procesado: {len(filas)} movimientos",
            ))

            return {
                "id_archivo": id_archivo,
                "estado": "PROCESADO",
                "registros": len(filas),
                "idempotente": False,
            }
