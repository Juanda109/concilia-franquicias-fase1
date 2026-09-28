class ArchivoRepository:
 """En parseo solo se actualiza ESTADO_PROCESAMIENTO: la creación del archivo y
 ESTADO_RECEPCION son responsabilidad exclusiva de back."""
 def __init__(self,conn): self.conn=conn
 def update_procesamiento(self,id_archivo,value,motivo=None):
  self.conn.execute("UPDATE CON_ARCHIVO_CARGA SET ESTADO_PROCESAMIENTO=%s,MOTIVO_ESTADO=%s,FECHA_CAMBIO_ESTADO=CURRENT_TIMESTAMP WHERE ID_ARCHIVO=%s",(value,motivo,id_archivo))
 def set_total(self,id_archivo,total):
  self.conn.execute("UPDATE CON_ARCHIVO_CARGA SET TOTAL_REGISTROS=%s WHERE ID_ARCHIVO=%s",(total,id_archivo))
 def set_progreso(self,id_archivo,procesados):
  self.conn.execute("UPDATE CON_ARCHIVO_CARGA SET REGISTROS_PROCESADOS=%s WHERE ID_ARCHIVO=%s",(procesados,id_archivo))
