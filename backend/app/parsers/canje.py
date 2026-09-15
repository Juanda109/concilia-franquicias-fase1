from pathlib import Path
from app.parsers.base import Parser
from app.ingestion.result import IngestionResult,RecordError
FIELDS=[('TX', 1, 2), ('BIN_DEST', 9, 6), ('FECHA_CANJE', 15, 6), ('TARJETA', 56, 19), ('VL_TOTAL', 123, 9), ('VL_INTERC_RAW', 141, 9), ('PLAZ', 150, 2), ('MOT_COB', 152, 2), ('COD_ERROR', 198, 2), ('MO_TO', 264, 1), ('IND_CASH', 265, 1), ('XX', 266, 2)]
def cut(line,start,length): return line[start-1:start-1+length]
class CanjeParser(Parser):
 def __init__(self,tipo_insumo): 
  if tipo_insumo not in ("CAET","CANT"): raise ValueError(tipo_insumo)
  self.tipo_insumo=tipo_insumo
 def parse(self,source:Path):
  r=IngestionResult(self.tipo_insumo)
  for n,line in enumerate(source.read_text(encoding="utf-8",errors="replace").splitlines(),start=1):
   if not line: continue
   if len(line)<267:r.errors.append(RecordError(n,None,"LONGITUD_INVALIDA",f"Longitud {len(line)}")); continue
   row={name:cut(line,st,ln).strip() for name,st,ln in FIELDS}; row["numero_linea"]=n
   raw=row["XX"]; row["ESPACIOS"]="MANUAL" if raw.strip()=="" else ("CNB" if raw in ("10","11","12") else "ELECTRONICO")
   r.records.append(row)
  r.controls.append({"codigo":"TOTAL_REGISTROS","obtenido":len(r.records)}); return r
