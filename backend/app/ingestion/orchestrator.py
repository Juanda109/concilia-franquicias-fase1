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
  ar.update_state(id_archivo,"ESTADO_VALIDACION","VALIDANDO");tr.add(id_archivo,"VALIDACION","NO_INICIADA","VALIDANDO","INICIO_VALIDACION",correlation_id)
  parser=get_parser(tipo)
  try: result=parser.parse(source)
  except Exception as exc:
   ar.update_state(id_archivo,"ESTADO_VALIDACION","ERROR_VALIDACION",str(exc));tr.add(id_archivo,"VALIDACION","VALIDANDO","ERROR_VALIDACION","ERROR_VALIDACION",correlation_id);raise
  if result.errors:
   er.save_many(id_archivo,tipo,"VALIDACION",correlation_id,result.errors);ar.update_state(id_archivo,"ESTADO_VALIDACION","ERROR_VALIDACION","Errores de registro");return result
  ar.update_state(id_archivo,"ESTADO_VALIDACION","VALIDADO");tr.add(id_archivo,"VALIDACION","VALIDANDO","VALIDADO","FIN_VALIDACION",correlation_id)
  ar.update_state(id_archivo,"ESTADO_PROCESAMIENTO","EN_PROCESO")
  ar.update_state(id_archivo,"ESTADO_PROCESAMIENTO","PROCESADO")
  ar.update_state(id_archivo,"ESTADO_CARGA","EN_CARGA")
  inserted=rr.insert_records(tipo,id_archivo,result.records)
  ar.update_state(id_archivo,"ESTADO_CARGA","CARGADO");ar.set_available(id_archivo,True)
  tr.add(id_archivo,"CARGA","EN_CARGA","CARGADO","FIN_CARGA",correlation_id,{"registros":inserted})
  return result
