from datetime import timedelta


class JornadaRepository:
 def __init__(self,conn): self.conn=conn
 def get_or_create(self,fecha_contable):
  row=self.conn.execute("SELECT ID_JORNADA FROM CON_JORNADA WHERE FECHA_CONTABLE=%s",(fecha_contable,)).fetchone()
  if row: return row[0]
  row=self.conn.execute("INSERT INTO CON_JORNADA(FECHA_CONTABLE,ESTADO,FECHA_INICIO) VALUES (%s,'Pendiente',CURRENT_TIMESTAMP) RETURNING ID_JORNADA",(fecha_contable,)).fetchone()
  return row[0]
 def get_or_create_rango(self,fecha_desde,fecha_hasta):
  """Una jornada por cada día del rango (inclusive), en orden ascendente -
  mismo contrato 1:1 fecha<->jornada que get_or_create, repetido día por día."""
  dias=(fecha_hasta-fecha_desde).days
  return [
   (fecha_desde+timedelta(days=i), self.get_or_create(fecha_desde+timedelta(days=i)))
   for i in range(dias+1)
  ]
 def resumen(self,id_jornada):
  return self.conn.execute("SELECT ID_JORNADA,FECHA_CONTABLE FROM CON_JORNADA WHERE ID_JORNADA=%s",(id_jornada,)).fetchone()
