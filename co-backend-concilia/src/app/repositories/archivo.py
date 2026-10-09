import uuid

def _acciones_permitidas(estado_recepcion,estado_procesamiento):
 acciones=[]
 if estado_procesamiento in ('Procesando','Procesado'): acciones.append('VER_CONTENIDO')
 if estado_recepcion=='No recibido' and estado_procesamiento!='Procesando': acciones.append('CARGAR_ARCHIVO_ORIGINAL')
 return acciones

class ArchivoRepository:
 def __init__(self,conn): self.conn=conn
 def update_state(self,id_archivo,field,value,motivo=None):
  allowed={"ESTADO_RECEPCION","ESTADO_PROCESAMIENTO"}
  if field not in allowed: raise ValueError(field)
  self.conn.execute(f"UPDATE CON_ARCHIVO_CARGA SET {field}=%s,MOTIVO_ESTADO=%s,FECHA_CAMBIO_ESTADO=CURRENT_TIMESTAMP WHERE ID_ARCHIVO=%s",(value,motivo,id_archivo))
 def get_or_create(self,id_jornada,id_insumo,nombre_archivo,correlation_id):
  row=self.conn.execute("SELECT ID_ARCHIVO FROM CON_ARCHIVO_CARGA WHERE ID_JORNADA=%s AND ID_INSUMO=%s",(id_jornada,id_insumo)).fetchone()
  if row: return row[0]
  row=self.conn.execute("""INSERT INTO CON_ARCHIVO_CARGA
 (ID_JORNADA,ID_INSUMO,NOMBRE_ARCHIVO,ESTADO_RECEPCION,ESTADO_PROCESAMIENTO,CORRELATION_ID)
 VALUES (%s,%s,%s,'Recibido','Pendiente',%s) RETURNING ID_ARCHIVO""",
   (id_jornada,id_insumo,nombre_archivo,correlation_id)).fetchone()
  return row[0]
 def ensure_insumos(self,id_jornada):
  """Pre-crea una fila CON_ARCHIVO_CARGA (placeholder, sin archivo) por cada
  insumo activo que todavía no tenga fila en esta jornada, para que todo
  insumo tenga un idArchivo estable desde que se resuelve la jornada,
  exista o no archivo físico recibido."""
  faltantes=self.conn.execute("""SELECT i.ID_INSUMO FROM CON_INSUMO_ESPERADO i
 WHERE i.ACTIVO AND NOT EXISTS (SELECT 1 FROM CON_ARCHIVO_CARGA a WHERE a.ID_JORNADA=%s AND a.ID_INSUMO=i.ID_INSUMO)""",(id_jornada,)).fetchall()
  for (id_insumo,) in faltantes:
   self.conn.execute("""INSERT INTO CON_ARCHIVO_CARGA
 (ID_JORNADA,ID_INSUMO,ESTADO_RECEPCION,ESTADO_PROCESAMIENTO,CORRELATION_ID)
 VALUES (%s,%s,'No recibido','Pendiente',%s)""",(id_jornada,id_insumo,str(uuid.uuid4())))
 def listar_insumos(self,id_jornada):
  rows=self.conn.execute("""SELECT a.ID_ARCHIVO,i.FUENTE,i.TIPO_INSUMO,a.NOMBRE_ARCHIVO,a.TOTAL_REGISTROS,
 a.ESTADO_RECEPCION,a.ESTADO_PROCESAMIENTO
 FROM CON_ARCHIVO_CARGA a JOIN CON_INSUMO_ESPERADO i ON i.ID_INSUMO=a.ID_INSUMO
 WHERE a.ID_JORNADA=%s ORDER BY i.ORDEN_VISUAL""",(id_jornada,)).fetchall()
  insumos=[]
  for id_archivo,fuente,tipo_insumo,nombre_archivo,total_registros,estado_recepcion,estado_procesamiento in rows:
   insumos.append({
    "idArchivo":id_archivo,"fuente":fuente,"tipoInsumo":tipo_insumo,"nombreArchivo":nombre_archivo,
    "totalRegistros":total_registros,"estadoRecepcion":estado_recepcion,"estadoProcesamiento":estado_procesamiento,
    "accionesPermitidas":_acciones_permitidas(estado_recepcion,estado_procesamiento),
   })
  return insumos
 def obtener_para_carga(self,id_archivo,id_jornada):
  row=self.conn.execute("""SELECT a.ID_JORNADA,a.ESTADO_RECEPCION,a.ESTADO_PROCESAMIENTO,a.CORRELATION_ID,i.TIPO_INSUMO
 FROM CON_ARCHIVO_CARGA a JOIN CON_INSUMO_ESPERADO i ON i.ID_INSUMO=a.ID_INSUMO WHERE a.ID_ARCHIVO=%s""",(id_archivo,)).fetchone()
  if not row: return None,None,'ARCHIVO_NO_ENCONTRADO'
  id_jornada_real,estado_recepcion,estado_procesamiento,correlation_id,tipo_insumo=row
  if id_jornada_real!=id_jornada: return None,None,'ARCHIVO_NO_PERTENECE_A_JORNADA'
  if 'CARGAR_ARCHIVO_ORIGINAL' not in _acciones_permitidas(estado_recepcion,estado_procesamiento):
   return None,None,'CARGA_NO_PERMITIDA'
  return tipo_insumo,correlation_id,None
 def marcar_recibido(self,id_archivo,nombre_archivo,correlation_id):
  self.conn.execute("""UPDATE CON_ARCHIVO_CARGA SET NOMBRE_ARCHIVO=%s,ESTADO_RECEPCION='Recibido',
 CORRELATION_ID=%s,FECHA_CAMBIO_ESTADO=CURRENT_TIMESTAMP WHERE ID_ARCHIVO=%s""",(nombre_archivo,correlation_id,id_archivo))
