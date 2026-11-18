"""Coordinador de procesamiento Host completo.

Coordina la persistencia normalizada y el detalle fuente.
Cada etapa conserva su propia transaccion para permitir recuperacion.
Los reintentos son responsabilidad del Host Loader; no se limita su cantidad.
"""

from app.repositories.database import connection
from psycopg import sql
from app.services.procesamiento_host import ProcesamientoHostError


TABLAS_HOST = {
    "HA22": "con_ha22_detalle",
    "HA26": "con_ha26_detalle",
    "HA32": "con_ha32_detalle",
}


class ProcesamientoHostCompletoError(ProcesamientoHostError):
    pass


def _verificar_persistencias(id_archivo, tipo, total_esperado):
    tabla = TABLAS_HOST[tipo]

    with connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    a.tipo_archivo,
                    a.estado,
                    a.total_registros,
                    i.estado,
                    i.id_jornada,
                    (
                        SELECT COUNT(*)
                        FROM public.con_host_resultado h
                        WHERE h.id_archivo = a.id_archivo
                    ),
                    (
                        SELECT COUNT(*)
                        FROM public.con_trazabilidad t
                        WHERE t.id_archivo = a.id_archivo
                          AND t.tipo_evento = 'ARCHIVO_PROCESADO'
                          AND t.componente = 'PROCESAMIENTO_HOST'
                    ),
                    (
                        SELECT COUNT(*)
                        FROM public.con_trazabilidad t
                        WHERE t.id_archivo = a.id_archivo
                          AND t.tipo_evento = 'DETALLE_PERSISTIDO'
                          AND t.componente = 'PROCESAMIENTO_DETALLE'
                    ),
                    (
                        SELECT COUNT(*)
                        FROM public.con_trazabilidad t
                        WHERE t.id_archivo = a.id_archivo
                          AND t.id_jornada = i.id_jornada
                          AND t.tipo_evento = 'DETALLE_PERSISTIDO'
                          AND t.componente = 'PROCESAMIENTO_DETALLE'
                    )
                FROM public.con_archivo_carga a
                JOIN public.con_insumo_esperado i
                  ON i.id_archivo = a.id_archivo
                WHERE a.id_archivo = %s
            """, (id_archivo,))

            fila = cur.fetchone()

            if fila is None:
                raise ProcesamientoHostCompletoError(
                    "Archivo Host no asociado a un insumo."
                )

            (
                tipo_bd,
                estado_archivo,
                total_bd,
                estado_insumo,
                id_jornada,
                normalizados,
                eventos_host,
                eventos_detalle,
                eventos_detalle_jornada,
            ) = fila

            cur.execute(
                sql.SQL("""
                    SELECT
                        COUNT(*),
                        COUNT(DISTINCT linea_origen)
                    FROM public.{}
                    WHERE id_archivo = %s
                """).format(sql.Identifier(tabla)),
                (id_archivo,),
            )

            detalle, lineas_distintas = cur.fetchone()

    if tipo_bd != tipo:
        raise ProcesamientoHostCompletoError(
            "El tipo de archivo cambio durante el procesamiento."
        )

    if estado_archivo != "PROCESADO" or estado_insumo != "PROCESADO":
        raise ProcesamientoHostCompletoError(
            "Los estados de archivo e insumo no quedaron PROCESADO."
        )

    if total_bd != total_esperado:
        raise ProcesamientoHostCompletoError(
            "El total del archivo cambio durante el procesamiento."
        )

    if normalizados != total_esperado:
        raise ProcesamientoHostCompletoError(
            "Persistencia normalizada incompleta."
        )

    if detalle != total_esperado or lineas_distintas != total_esperado:
        raise ProcesamientoHostCompletoError(
            "Persistencia del detalle Host incompleta o duplicada."
        )

    if eventos_host != 1:
        raise ProcesamientoHostCompletoError(
            "Trazabilidad de procesamiento Host inconsistente."
        )

    if eventos_detalle != 1 or eventos_detalle_jornada != 1:
        raise ProcesamientoHostCompletoError(
            "Trazabilidad del detalle Host inconsistente."
        )

    return {
        "id_jornada": id_jornada,
        "normalizados": normalizados,
        "detalles": detalle,
        "lineas_distintas": lineas_distintas,
        "eventos_host": eventos_host,
        "eventos_detalle": eventos_detalle,
    }


def procesar_host_completo(id_archivo: int):
    """Completa ambas persistencias y permite reanudar ejecuciones.

    Primera etapa:
        procesar_host: persiste o reconoce CON_HOST_RESULTADO.

    Segunda etapa:
        persistir_detalle: persiste o reconoce el snapshot original.

    Si la segunda etapa falla, la primera queda confirmada.
    La siguiente invocacion reconoce la primera etapa como idempotente
    y vuelve a intentar la segunda.
    """

    if not isinstance(id_archivo, int) or isinstance(id_archivo, bool):
        raise ProcesamientoHostCompletoError(
            "Identificador de archivo invalido."
        )

    if id_archivo <= 0:
        raise ProcesamientoHostCompletoError(
            "Identificador de archivo debe ser positivo."
        )

    # Importacion en ejecucion para conservar los puntos de prueba
    # y permitir sustituir cada etapa independientemente.
    from app.services.procesamiento_host import procesar_host
    from app.services.persistencia_detalle import DetalleError, persistir_detalle

    resultado_host = procesar_host(id_archivo)

    if resultado_host.get("id_archivo") != id_archivo:
        raise ProcesamientoHostCompletoError(
            "La primera etapa devolvio otro archivo."
        )

    tipo = resultado_host.get("tipo_archivo")

    if tipo not in TABLAS_HOST:
        raise ProcesamientoHostCompletoError(
            "La primera etapa no devolvio un tipo Host valido."
        )

    registros_host = resultado_host.get("registros")

    if not isinstance(registros_host, int) or registros_host <= 0:
        raise ProcesamientoHostCompletoError(
            "La cantidad de resultados normalizados es invalida."
        )

    # Segunda etapa: tambien se ejecuta cuando el archivo ya estaba
    # PROCESADO. Esto permite reparar el detalle historico pendiente.
    try:
        resultado_detalle = persistir_detalle(id_archivo)
    except DetalleError as exc:
        raise ProcesamientoHostCompletoError(
            f"Persistencia del detalle Host fallida: {exc}"
        ) from exc

    if resultado_detalle.get("id_archivo") != id_archivo:
        raise ProcesamientoHostCompletoError(
            "La segunda etapa devolvio otro archivo."
        )

    if resultado_detalle.get("tipo") != tipo:
        raise ProcesamientoHostCompletoError(
            "Los tipos de las dos persistencias no coinciden."
        )

    registros_detalle = resultado_detalle.get("registros")

    if registros_detalle != registros_host:
        raise ProcesamientoHostCompletoError(
            "Las cantidades normalizadas y originales no coinciden."
        )

    auditoria = _verificar_persistencias(
        id_archivo,
        tipo,
        registros_host,
    )

    return {
        "id_archivo": id_archivo,
        "id_jornada": auditoria["id_jornada"],
        "tipo_archivo": tipo,
        "estado": "HOST_COMPLETO",
        "registros": registros_host,
        "idempotente": (
            resultado_host.get("idempotente") is True
            and resultado_detalle.get("idempotente") is True
        ),
        "etapas": {
            "normalizacion": resultado_host,
            "detalle": resultado_detalle,
        },
        "verificacion": auditoria,
    }
