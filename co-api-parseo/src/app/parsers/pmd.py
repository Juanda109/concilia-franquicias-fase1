from pathlib import Path
import xlrd
from app.parsers.base import Parser
from app.ingestion.result import IngestionResult,RecordError

SHEET="PMD"
# (campo,es_entero) en el orden real de columnas C..M de la hoja PMD
MEDIDAS=[
 ("debito_cantidad",True),("debito_valor",False),
 ("debito_comision_intercambio",False),("debito_comision_admin",False),("debito_neto",False),
 ("credito_cantidad",True),("credito_valor",False),
 ("credito_comision_intercambio",False),("credito_comision_admin",False),("credito_neto",False),
 ("total",False),
]

def _medida(ws,fila,col,campo,es_entero,numero_linea,diagnosticos):
 """Blanco, cero y error de Excel NO son equivalentes (regla PMD-F1-004):
 blanco -> None (el NULL en BD ya lo distingue de 0); error de Excel
 (#N/A, #REF!, etc.) -> None + se registra en diagnosticos (se persiste en
 CON_ERROR_REGISTRO sin bloquear el resto de la fila); cero -> 0 real."""
 tipo=ws.cell_type(fila,col)
 if tipo in (xlrd.XL_CELL_EMPTY,xlrd.XL_CELL_BLANK): return None
 if tipo==xlrd.XL_CELL_ERROR:
  texto=xlrd.error_text_from_code.get(ws.cell_value(fila,col),"#ERROR")
  diagnosticos.append(RecordError(numero_linea,campo,"VALOR_ERROR_EXCEL",f"Celda con error de Excel: {texto}",texto))
  return None
 valor=ws.cell_value(fila,col)
 return int(round(valor)) if es_entero else valor

class PMDParser(Parser):
 tipo_insumo="PMD"
 def parse(self,source:Path):
  r=IngestionResult(self.tipo_insumo)
  wb=xlrd.open_workbook(str(source))
  if SHEET not in wb.sheet_names():
   r.errors.append(RecordError(None,None,"HOJA_NO_ENCONTRADA",SHEET)); return r
  ws=wb.sheet_by_name(SHEET)
  # Fila 1 = encabezados de grupo (DEBITO/CREDITO/Total), fila 2 = etiquetas
  # de medida (Cantidad/Valor/...), los registros empiezan en la fila 3.
  for fila in range(2,ws.nrows):
   numero_linea=fila+1
   producto=str(ws.cell_value(fila,0)).strip()
   nivel=str(ws.cell_value(fila,1)).strip()
   if not producto and not nivel: continue
   rec={"numero_linea":numero_linea,"producto_servicio":producto,"nivel":nivel}
   for idx,(campo,es_entero) in enumerate(MEDIDAS,start=2):
    rec[campo]=_medida(ws,fila,idx,campo,es_entero,numero_linea,r.diagnosticos)
   r.records.append(rec)
  r.controls.append({"codigo":"TOTAL_REGISTROS","obtenido":len(r.records)})
  if r.diagnosticos:
   r.controls.append({"codigo":"CELDAS_CON_ERROR_EXCEL","obtenido":len(r.diagnosticos)})
  return r
