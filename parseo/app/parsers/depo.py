from datetime import date
from pathlib import Path
from app.parsers.base import Parser
from app.ingestion.result import IngestionResult
FIELDS=[('TIPO_MOVIMIENTO', 1, 2), ('BIN_FUENTE', 3, 6), ('BIN_DESTINO', 9, 6), ('FECHA_DEL_CANJE', 15, 6), ('NUMERO_DEL_LOTE', 21, 3), ('NUMERO_DEL_REGISTRO', 24, 6), ('BIN_RECEPTOR', 30, 6), ('FECHA_CONTABILIZACION', 36, 6), ('NUMERO_SECUENCIA', 42, 9), ('DIGITO_CHEQUEO', 51, 1), ('COD_OFICINA', 52, 4), ('NO_TARJETA', 56, 19), ('NO_COMPROBANTE', 75, 4), ('FECHA_COMPROBANTE', 79, 6), ('COD_COMERCIO', 85, 10), ('PORCENTAJE_DESCUENTO', 95, 4), ('COD_AUTORIZACION', 99, 6), ('VALOR_COMPRA', 105, 9), ('VALOR_PROPINA', 114, 9), ('VALOR_TOTAL', 123, 9), ('VALOR_DESCUENTO', 132, 9), ('VALOR_INTERCAMBIO', 141, 9), ('PLAZO', 150, 2), ('MOTIVO_COBRO', 152, 2), ('TX_ANTERIOR', 154, 2), ('CAPTURA', 156, 1), ('FECHA_DE_DEPOSITO', 157, 6), ('CUENTA_DE_DEPOSITO', 163, 18), ('NUMERO_DE_TERMINAL', 181, 5), ('CODIGO_ALTERNO', 186, 10), ('TIPO_DE_RED', 196, 1), ('IDENTIFICADOR_RED_ADQUIRENTE', 197, 1), ('COD_DE_ERROR', 198, 2), ('IDENTIFICADOR_REG_INCONSISTENTE', 200, 1), ('VALOR_DEL_IVA_VLOR_TRANSF', 201, 9), ('VLOR_RETENCION_COMPRA', 210, 9), ('VLOR_RETENCION_IVA', 219, 9), ('VALOR_DEPOSITO_NETO', 228, 9), ('VALOR_ICA', 237, 9), ('VALOR_INTERCAMBIO_2', 246, 9), ('VALOR_IVA_A_RETORNAR', 255, 9), ('INDICADOR_MO_TO_O_COMERCIO_ELECTRO', 264, 1), ('INDICADOR_CASH_BACK', 265, 3), ('ESPACIOS', 268, 15)]
def cut(line,start,length): return line[start-1:start-1+length]
# Columnas NUMERIC(24,4) en el DDL (13_con_deposito_resultado.sql): quedan en
# blanco (espacios) cuando el movimiento no aplica ese valor, y tras el strip()
# llegan como "" — Postgres no castea "" a NUMERIC, hay que mandar NULL.
NUMERIC_FIELDS=["VALOR_COMPRA","VALOR_PROPINA","VALOR_TOTAL","VALOR_DESCUENTO","VALOR_INTERCAMBIO","VALOR_DEL_IVA_VLOR_TRANSF","VALOR_DEPOSITO_NETO","VALOR_ICA","VALOR_INTERCAMBIO_2","VALOR_IVA_A_RETORNAR"]
def _fecha_comprobante(v):
 """FECHA_COMPROBANTE es la única columna de este insumo tipada DATE en el DDL
 (las demás FECHA_* quedan como VARCHAR); "000000" u otras fechas inválidas se
 usan como sentinela de "sin fecha" en el archivo origen y deben ir como NULL,
 no como string crudo, o Postgres rechaza el INSERT completo."""
 if not v or len(v)!=6 or not v.isdigit(): return None
 try: return date(2000+int(v[0:2]),int(v[2:4]),int(v[4:6])).isoformat()
 except ValueError: return None
class DEPOParser(Parser):
 tipo_insumo="DEPO"
 def parse(self,source:Path):
  r=IngestionResult(self.tipo_insumo)
  for n,line in enumerate(source.read_text(encoding="utf-8",errors="replace").splitlines(),start=1):
   if not line:continue
   padded=line.ljust(282)
   row={name:cut(padded,st,ln).strip() for name,st,ln in FIELDS};row["numero_linea"]=n;row["_longitud_fisica"]=len(line)
   row["FECHA_COMPROBANTE"]=_fecha_comprobante(row["FECHA_COMPROBANTE"])
   for f in NUMERIC_FIELDS:
    if row[f]=="":row[f]=None
   r.records.append(row)
  r.controls.append({"codigo":"TOTAL_REGISTROS","obtenido":len(r.records)});return r
