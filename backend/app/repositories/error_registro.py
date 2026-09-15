class ErrorRegistroRepository:
 def __init__(self,conn):self.conn=conn
 def save_many(self,id_archivo,tipo,etapa,correlation_id,errors):
  self.conn.execute("DELETE FROM CON_ERROR_REGISTRO WHERE ID_ARCHIVO=%s AND ETAPA=%s",(id_archivo,etapa))
  for e in errors:self.conn.execute("""INSERT INTO CON_ERROR_REGISTRO(ID_ARCHIVO,NUMERO_LINEA,TIPO_INSUMO,ETAPA,CAMPO,VALOR_ORIGEN,CODIGO_ERROR,MENSAJE,CORRELATION_ID)
 VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",(id_archivo,e.numero_linea,tipo,etapa,e.campo,e.valor_origen,e.codigo,e.mensaje,correlation_id))
