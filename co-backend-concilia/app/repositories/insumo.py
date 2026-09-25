class InsumoRepository:
 def __init__(self,conn): self.conn=conn
 def get_by_tipo(self,tipo_insumo):
  row=self.conn.execute("SELECT ID_INSUMO,PATRON_ARCHIVO FROM CON_INSUMO_ESPERADO WHERE TIPO_INSUMO=%s AND ACTIVO",(tipo_insumo,)).fetchone()
  return {"id_insumo":row[0],"patron_archivo":row[1]} if row else None
