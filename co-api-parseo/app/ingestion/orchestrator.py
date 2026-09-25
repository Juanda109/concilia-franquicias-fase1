from app.ingestion.registry import get_parser
from app.repositories.archivo import ArchivoRepository
from app.repositories.error_registro import ErrorRegistroRepository
from app.repositories.trazabilidad import TrazabilidadRepository
from app.repositories.resultados.generic import ResultRepository
from app.clients.minio_client import descargar

class ParseoOrchestrator:
 def __init__(self,conn): self.conn=conn
 def execute(self,id_archivo,tipo,minio_key:str,correlation_id:str):
  ar=ArchivoRepository(self.conn); er=ErrorRegistroRepository(self.conn); tr=TrazabilidadRepository(self.conn); rr=ResultRepository(self.conn)
  parser=get_parser(tipo)  # KeyError (tipo no soportado) se deja subir sin marcar estado: es un error del llamador, no del procesamiento
  ar.update_procesamiento(id_archivo,"Procesando");tr.add(id_archivo,"PROCESAMIENTO","Pendiente","Procesando","INICIO_PROCESAMIENTO",correlation_id)
  self.conn.commit()  # visible de inmediato a otras conexiones (polling de progreso desde back)
  source=None
  try:
   try:
    source=descargar(minio_key)
    result=parser.parse(source)
    ar.set_total(id_archivo,len(result.records));self.conn.commit()
   except Exception as exc:
    ar.update_procesamiento(id_archivo,"Error",str(exc));tr.add(id_archivo,"PROCESAMIENTO","Procesando","Error","ERROR_PROCESAMIENTO",correlation_id);self.conn.commit();raise
   if result.errors:
    er.save_many(id_archivo,tipo,"PROCESAMIENTO",correlation_id,result.errors);ar.update_procesamiento(id_archivo,"Error","Errores de registro");tr.add(id_archivo,"PROCESAMIENTO","Procesando","Error","ERROR_PROCESAMIENTO",correlation_id);self.conn.commit();return result
   def _progreso(n):
    ar.set_progreso(id_archivo,n);self.conn.commit()
   inserted=rr.insert_records(tipo,id_archivo,result.records,on_progress=_progreso)
   ar.update_procesamiento(id_archivo,"Procesado")
   tr.add(id_archivo,"PROCESAMIENTO","Procesando","Procesado","FIN_PROCESAMIENTO",correlation_id,{"registros":inserted})
   self.conn.commit()
   return result
  finally:
   if source: source.unlink(missing_ok=True)
