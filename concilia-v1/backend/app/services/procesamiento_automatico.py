"""Orquestacion de procesamiento automatico, sin consolidacion contable."""
import logging
from app.repositories.database import connection

LOG = logging.getLogger(__name__)
HOST = frozenset(('HA22','HA26','HA32'))

def procesar_jornada_si_lista(id_jornada: int):
    # La conexion conserva el advisory lock durante toda la ejecucion.
    with connection() as lock_conn:
        with lock_conn.cursor() as cur:
            cur.execute('SELECT pg_try_advisory_lock(%s)',(int(id_jornada),))
            if not cur.fetchone()[0]:
                return {'estado':'OTRO_PROCESO_ACTIVO'}
        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute('SET TRANSACTION READ ONLY')
                    cur.execute("""SELECT j.estado,i.tipo_insumo,i.estado,i.id_archivo,
                                          a.total_registros,i.obligatorio,
                                          EXISTS(SELECT 1 FROM con_confirmacion_sin_movimientos c
                                                 WHERE c.id_archivo=i.id_archivo)
                                   FROM con_jornada j JOIN con_insumo_esperado i
                                     ON i.id_jornada=j.id_jornada
                                   LEFT JOIN con_archivo_carga a ON a.id_archivo=i.id_archivo
                                   WHERE j.id_jornada=%s""",(id_jornada,))
                    filas=cur.fetchall()
            if not filas or filas[0][0]=='COMPLETADA':
                return {'estado':'NO_APLICA'}
            # Se procesan insumos validos solo cuando todos los obligatorios
            # tienen archivo recibido o confirmacion explicita de cero.
            obligatorios=[r for r in filas if r[5] and r[1]!='MEP']
            if not obligatorios or any(r[3] is None or (r[4]==0 and not r[6])
                                      or r[2] not in ('RECIBIDO','PROCESADO')
                                      for r in obligatorios):
                return {'estado':'ESPERANDO_OBLIGATORIOS'}
            procesados = []
            parciales = []
            errores = []
            for _,tipo,estado,archivo,total,obligatorio,confirmado in filas:
                if estado!='RECIBIDO' or archivo is None or confirmado or total==0:
                    continue
                try:
                    if tipo in HOST:
                        # El Host Loader conserva su politica de reintentos indefinidos.
                        from app.services.procesamiento_host import procesar_host
                        procesar_host(archivo)
                    else:
                        from app.api.procesamiento_franquicias import ejecutar_franquicia
                        resultado = ejecutar_franquicia(archivo)
                    procesados.append(archivo)
                except Exception as exc:
                    LOG.exception('Fallo procesamiento automatico archivo %s',archivo)
                    errores.append({'tipo': tipo, 'id_archivo': archivo,
                                   'error': str(exc)})
            return {'estado': ('EJECUCION_PARCIAL' if errores or parciales
                               else 'EJECUCION_FINALIZADA'),
                    'procesados': procesados, 'parciales': parciales,
                    'errores': errores}
        finally:
            with lock_conn.cursor() as cur:
                cur.execute('SELECT pg_advisory_unlock(%s)',(int(id_jornada),))
