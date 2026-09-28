class JornadaRepository:
 def __init__(self,conn): self.conn=conn
 def get_or_create(self,fecha_contable):
  row=self.conn.execute("SELECT ID_JORNADA FROM CON_JORNADA WHERE FECHA_CONTABLE=%s",(fecha_contable,)).fetchone()
  if row: return row[0]
  row=self.conn.execute("INSERT INTO CON_JORNADA(FECHA_CONTABLE,ESTADO,FECHA_INICIO) VALUES (%s,'Pendiente',CURRENT_TIMESTAMP) RETURNING ID_JORNADA",(fecha_contable,)).fetchone()
  return row[0]
