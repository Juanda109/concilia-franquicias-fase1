from psycopg.types.json import Jsonb

class TrazabilidadRepository:
    """Eventos originados por una accion humana (carga, rechazo, eliminacion)
    desde el backend, en la misma tabla que co-api-parseo usa para sus
    eventos automaticos de procesamiento (ETAPA='PROCESAMIENTO') - aqui
    siempre con ETAPA='RECEPCION' y con el usuario que la origino."""
    def __init__(self, conn):
        self.conn = conn

    def add(self, id_archivo, anterior, nuevo, evento, correlation_id, usuario, detalle=None):
        self.conn.execute(
            """INSERT INTO CON_TRAZABILIDAD
 (ID_ARCHIVO,ETAPA,ESTADO_ANTERIOR,ESTADO_NUEVO,EVENTO,CORRELATION_ID,USUARIO_SUB,USUARIO_EMAIL,DETALLE)
 VALUES (%s,'RECEPCION',%s,%s,%s,%s,%s,%s,%s)""",
            (id_archivo, anterior, nuevo, evento, correlation_id,
             (usuario or {}).get('sub'), (usuario or {}).get('email'),
             Jsonb(detalle) if detalle is not None else None))
