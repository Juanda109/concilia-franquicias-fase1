from pathlib import Path
from app.ingestion.registry import get_parser
from app.repositories.archivo import ArchivoRepository
from app.repositories.error_registro import ErrorRegistroRepository
from app.repositories.trazabilidad import TrazabilidadRepository
from app.repositories.resultados.generic import ResultRepository

class IngestionOrchestrator:
 def __init__(self,conn): self.conn=conn
 def execute(self,id_archivo,tipo,source:Path,correlation_id:str):
  ar=ArchivoRepository(self.conn); er=ErrorRegistroRepository(self.conn); tr=TrazabilidadRepository(self.conn); rr=ResultRepository(self.conn)
  ar.update_state(id_archivo,"ESTADO_PROCESAMIENTO","Procesando");tr.add(id_archivo,"PROCESAMIENTO","Pendiente","Procesando","INICIO_PROCESAMIENTO",correlation_id)
  parser=get_parser(tipo)
  try: result=parser.parse(source)
  except Exception as exc:
   ar.update_state(id_archivo,"ESTADO_PROCESAMIENTO","Error",str(exc));tr.add(id_archivo,"PROCESAMIENTO","Procesando","Error","ERROR_PROCESAMIENTO",correlation_id);raise
  if result.errors:
   er.save_many(id_archivo,tipo,"PROCESAMIENTO",correlation_id,result.errors);ar.update_state(id_archivo,"ESTADO_PROCESAMIENTO","Error","Errores de registro");tr.add(id_archivo,"PROCESAMIENTO","Procesando","Error","ERROR_PROCESAMIENTO",correlation_id);return result
  inserted=rr.insert_records(tipo,id_archivo,result.records)
  ar.update_state(id_archivo,"ESTADO_PROCESAMIENTO","Procesado");ar.set_available(id_archivo,True)
  tr.add(id_archivo,"PROCESAMIENTO","Procesando","Procesado","FIN_PROCESAMIENTO",correlation_id,{"registros":inserted})
  return result
