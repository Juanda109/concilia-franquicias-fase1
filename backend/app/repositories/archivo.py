class ArchivoRepository:
 def __init__(self,conn): self.conn=conn
 def update_state(self,id_archivo,field,value,motivo=None):
  allowed={"ESTADO_RECEPCION","ESTADO_PROCESAMIENTO","ESTADO_DISPONIBILIDAD"}
  if field not in allowed: raise ValueError(field)
  self.conn.execute(f"UPDATE CON_ARCHIVO_CARGA SET {field}=%s,MOTIVO_ESTADO=%s,FECHA_CAMBIO_ESTADO=CURRENT_TIMESTAMP WHERE ID_ARCHIVO=%s",(value,motivo,id_archivo))
 def set_available(self,id_archivo,value=True):
  self.conn.execute("UPDATE CON_ARCHIVO_CARGA SET DISPONIBLE=%s,ESTADO_DISPONIBILIDAD=%s WHERE ID_ARCHIVO=%s",(value,"Disponible" if value else "No disponible",id_archivo))
 def get_or_create(self,id_jornada,id_insumo,nombre_archivo,correlation_id):
  row=self.conn.execute("SELECT ID_ARCHIVO FROM CON_ARCHIVO_CARGA WHERE ID_JORNADA=%s AND ID_INSUMO=%s",(id_jornada,id_insumo)).fetchone()
  if row: return row[0]
  row=self.conn.execute("""INSERT INTO CON_ARCHIVO_CARGA
 (ID_JORNADA,ID_INSUMO,NOMBRE_ARCHIVO,ESTADO_RECEPCION,ESTADO_PROCESAMIENTO,ESTADO_DISPONIBILIDAD,CORRELATION_ID)
 VALUES (%s,%s,%s,'Recibido','Pendiente','No disponible',%s) RETURNING ID_ARCHIVO""",
   (id_jornada,id_insumo,nombre_archivo,correlation_id)).fetchone()
  return row[0]
