"""Procesamiento individual automatico Fase 1; sin conciliacion contable."""
import logging
from app.repositories.database import connection

LOG = logging.getLogger(__name__)
HOST = frozenset(("HA22", "HA26", "HA32"))


def procesar_archivo_recibido_f1(id_jornada: int, id_archivo: int):
    """Solo procesa el archivo vigente, con movimientos y sin confirmacion de cero."""
    with connection() as lock_conn:
        with lock_conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (int(id_jornada),))
            if not cur.fetchone()[0]:
                # Otro proceso de jornada ya tiene el bloqueo: no duplicar trabajo.
                return {"estado": "OTRO_PROCESO_ACTIVO"}
        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SET TRANSACTION READ ONLY")
                    cur.execute("""
                        SELECT j.estado, i.tipo_insumo, i.estado, a.estado,
                               a.total_registros,
                               EXISTS (SELECT 1 FROM con_confirmacion_sin_movimientos c
                                       WHERE c.id_archivo = a.id_archivo)
                        FROM con_jornada j
                        JOIN con_insumo_esperado i ON i.id_jornada = j.id_jornada
                        JOIN con_archivo_carga a ON a.id_archivo = i.id_archivo
                        WHERE j.id_jornada = %s AND a.id_archivo = %s
                    """, (id_jornada, id_archivo))
                    fila = cur.fetchone()
            if not fila:
                return {"estado": "ARCHIVO_REEMPLAZADO_O_NO_ASOCIADO"}
            jornada_estado, tipo, insumo_estado, archivo_estado, total, confirmado = fila
            if jornada_estado == "COMPLETADA":
                return {"estado": "JORNADA_COMPLETADA"}
            if insumo_estado != "RECIBIDO" or archivo_estado != "RECIBIDO":
                return {"estado": "NO_APLICA"}
            if confirmado or total is None or total <= 0:
                return {"estado": "ESPERANDO_CONFIRMACION_SIN_MOVIMIENTOS"}
            try:
                if tipo in HOST:
                    # No imponer limite de reintentos al Host Loader existente.
                    from app.services.procesamiento_host import procesar_host
                    resultado = procesar_host(id_archivo)
                else:
                    from app.api.procesamiento_franquicias import ejecutar_franquicia
                    resultado = ejecutar_franquicia(id_archivo)
                return {"estado": "PROCESADO", "id_archivo": id_archivo, "resultado": resultado}
            except Exception:
                LOG.exception("Fallo ingesta automatica F1 archivo %s", id_archivo)
                return {"estado": "ERROR_PROCESAMIENTO", "id_archivo": id_archivo}
        finally:
            with lock_conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (int(id_jornada),))
