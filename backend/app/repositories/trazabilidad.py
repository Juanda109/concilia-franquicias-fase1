from psycopg.types.json import Jsonb

class TrazabilidadRepository:
 def __init__(self,conn):self.conn=conn
 def add(self,id_archivo,etapa,anterior,nuevo,evento,correlation_id,detalle=None):
  self.conn.execute("""INSERT INTO CON_TRAZABILIDAD(ID_ARCHIVO,ETAPA,ESTADO_ANTERIOR,ESTADO_NUEVO,EVENTO,CORRELATION_ID,DETALLE)
 VALUES(%s,%s,%s,%s,%s,%s,%s)""",(id_archivo,etapa,anterior,nuevo,evento,correlation_id,Jsonb(detalle) if detalle is not None else None))
