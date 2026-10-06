from pathlib import Path
from app.parsers.base import Parser
from app.ingestion.result import IngestionResult,RecordError
FIELDS=[('TX', 1, 2), ('BIN_DEST', 9, 6), ('FECHA_CANJE', 15, 6), ('TARJETA', 56, 19), ('VL_TOTAL', 123, 9), ('VL_INTERC_RAW', 141, 9), ('PLAZ', 150, 2), ('MOT_COB', 152, 2), ('COD_ERROR', 198, 2), ('MO_TO', 264, 1), ('IND_CASH', 265, 1), ('XX', 266, 2)]
def cut(line,start,length): return line[start-1:start-1+length]
# Columnas NUMERIC(24,4) en el DDL (12_con_canje_resultado.sql): en blanco
# cuando el movimiento no aplica ese valor -> "" tras el strip(), Postgres no
# lo castea a NUMERIC (mismo problema ya resuelto en DEPO).
NUMERIC_FIELDS=["VL_TOTAL","VL_INTERC"]
def _tx_normalizado(tx):
 """Regla 3.1/3.2: TX impar -> "Totales" (línea de totales, no transacción
 real); TX par -> se deja el código tal cual."""
 if tx.isdigit() and int(tx)%2==1: return "Totales"
 return tx
def _comision_op_exitosas(tx,bin_dest):
 """Regla 3.7: TX='02' y BIN_DEST<>'439467' -> comisión fija de operación
 exitosa. OJO: se evalúa contra el TX ya normalizado — no cambia el
 resultado para '02' (es par, _tx_normalizado no lo toca), pero hay que
 tenerlo presente si se agregan más códigos pares a esta regla más adelante."""
 return 7450 if tx=="02" and bin_dest!="439467" else None
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
   row["TX"]=_tx_normalizado(row["TX"])
   row["COMISION_OP_EXITOSAS"]=_comision_op_exitosas(row["TX"],row["BIN_DEST"])
   # VL_INTERC_RAW -> VL_INTERC: la columna real de CON_CANJE_RESULTADO no
   # lleva el sufijo "_RAW" (por eso fallaba el INSERT). Pendiente: la regla
   # de negocio invierte el signo cuando TX='22' y TIPO='EFIPAGO' (matriz de
   # mapeo, hoja Reglas_clave) — TIPO sale de un catálogo de BINES que todavía
   # no existe en el proyecto, así que por ahora se guarda el valor crudo.
   row["VL_INTERC"]=row.pop("VL_INTERC_RAW")
   for f in NUMERIC_FIELDS:
    if row[f]=="":row[f]=None
   r.records.append(row)
  r.controls.append({"codigo":"TOTAL_REGISTROS","obtenido":len(r.records)}); return r
