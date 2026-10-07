from pathlib import Path
from app.parsers.base import Parser
from app.ingestion.result import IngestionResult,RecordError

FIELDS=[('TX', 1, 2), ('BIN_DEST', 9, 6), ('FECHA_CANJE', 15, 6), ('TARJETA', 56, 19), ('VL_TOTAL', 123, 9), ('VL_INTERC_RAW', 141, 9), ('PLAZ', 150, 2), ('MOT_COB', 152, 2), ('COD_ERROR', 198, 2), ('MO_TO', 264, 1), ('IND_CASH', 265, 1), ('XX', 266, 2)]
def cut(line,start,length): return line[start-1:start-1+length]

# Columnas NUMERIC(24,4) en el DDL (12_con_canje_resultado.sql): en blanco
# cuando el movimiento no aplica ese valor -> "" tras el strip(), Postgres no
# lo castea a NUMERIC (mismo problema ya resuelto en DEPO).
NUMERIC_FIELDS=["VL_TOTAL","VL_INTERC","COMISION_OP_EXITOSAS","TII_RECIBIDA_EMISOR_VISA_OP_REVER_VENTAS"]

# Catálogo BIN -> TIPO, extraído de la hoja "BINES" (columnas D:E) del Excel
# real "ESTRUCTURA CANJE ELECTRONICO Y MANUAL CORTO_OK.xlsx". La fórmula
# original es VLOOKUP(VALUE(MID(TARJETA,4,6)), BINES!D3:E45, 2, 0).
BINES_TIPO={
 404279:"DEBITO",404280:"CREDITO",410164:"CREDITO",421892:"CREDITO",439467:"EFIPAGO",
 450407:"CREDITO",450408:"CREDITO",450418:"CREDITO",454100:"CREDITO",454759:"CREDITO",
 455100:"CREDITO",457316:"DEBITO",483080:"CREDITO",451309:"CREDITO",456783:"CREDITO",
 462550:"DEBITO",485995:"CREDITO",491268:"DEBITO",492468:"DEBITO",492488:"CREDITO",
 492489:"CREDITO",518761:"CREDITO",518841:"CREDITO",527564:"CREDITO",540699:"CREDITO",
 542650:"CREDITO",547457:"CREDITO",548115:"CREDITO",553643:"CREDITO",589515:"DEBITO",
 813001:"CREDITO",459418:"CREDITO",459419:"CREDITO",441015:"VISA VALE",441016:"VISA VALE",
 432346:"DEBITO",459317:"DEBITO",418253:"DEBITO",457021:"CREDITO",432345:"CREDITO",
 487507:"CREDITO",417704:"DEBITO",
}

def _tx_normalizado(tx):
 """TX impar -> "Totales" (línea de totales, no transacción real); TX par ->
 se deja el código tal cual. =IFERROR(IF(ISODD(MID(plano,1,2)),"Totales",MID(plano,1,2)),"")"""
 if tx.isdigit() and int(tx)%2==1: return "Totales"
 return tx

def _canal(tx_normalizado,xx):
 """=IF(ISODD(TX),"Totales",IF(XX="  ","Manual",IF(XX IN (10,11,12),"CNB","ELECTRONICO")))
 OJO: usa el mismo criterio de TX impar que ya decide "Totales" — por eso se
 reutiliza tx_normalizado en vez de recalcular la paridad aparte."""
 if tx_normalizado=="Totales": return "Totales"
 if xx.strip()=="": return "Manual"
 if xx in ("10","11","12"): return "CNB"
 return "ELECTRONICO"

def _tipo(tarjeta):
 """=IFERROR(VLOOKUP(VALUE(MID(TARJETA,4,6)),BINES!$D$3:$E$45,2,0),"")
 MID(TARJETA,4,6) en Excel (1-based) = TARJETA[3:9] en Python (0-based)."""
 bin_str=tarjeta[3:9]
 if not bin_str.isdigit(): return ""
 return BINES_TIPO.get(int(bin_str),"")

def _vl_interc(tx,tipo,vl_interc_raw):
 """=IF(AND(TX="22",TIPO="EFIPAGO"),RAW*-1,RAW*1)"""
 if not vl_interc_raw: return None
 try: valor=int(vl_interc_raw)
 except ValueError: return None
 return -valor if (tx=="22" and tipo=="EFIPAGO") else valor

def _comision_op_exitosas(tx,bin_dest):
 """=IF(AND(TX="02",BIN_DEST<>"439467"),7450,"")"""
 return 7450 if tx=="02" and bin_dest!="439467" else None

def _tii_recibida(tipo,tx,vl_total,vl_interc):
 """=IF(AND(TIPO="CREDITO",TX="26"),VL_TOTAL-VL_INTERC,"")"""
 if tipo=="CREDITO" and tx=="26":
  total=int(vl_total) if vl_total!="" else 0
  interc=vl_interc or 0
  return total-interc
 return None

def _cuenta(cod_error,tipo,canal,tx,bin_dest,mot_cob):
 """Clasificador ordenado (26 ramas) de la columna "cuenta" de la hoja
 "parte" del Excel real — primera condición que haga match, gana. Vacía si
 COD_ERROR<>'00' (se evalúa antes que todo lo demás), o si ninguna rama aplica."""
 if cod_error!="00": return ""
 D,C,T,B,P,K=tipo,canal,tx,bin_dest,canal,mot_cob  # alias cortos, un ojo al original de Excel
 if D=="DEBITO" and P!="CNB" and T in ("02","06"): return "017-CANJE RECIBIDO TARJETA DEBITO"
 if D=="DEBITO" and B!="404279" and P!="CNB" and T=="04": return "017-ORIGINAL PAGOS A TARJETAS DEBITO"
 if D=="DEBITO" and B=="404279" and P!="CNB" and T in ("04","22","26"): return "017-ORIGINAL PAGOS A TARJETAS DEBITO"
 if D=="DEBITO" and B!="404279" and B!="462550" and P!="CNB" and T in ("22","26"): return "017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES"
 if D=="DEBITO" and B=="462550" and P!="CNB" and T in ("22","26"): return "017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES REGALO"
 if D=="DEBITO" and B!="404279" and P!="CNB" and T=="24": return "017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES PAGOS"
 if D=="DEBITO" and P=="CNB": return "017-OP CNBS"
 if D=="CREDITO" and T=="16": return "017-DEVOLUCION VTA NAL"
 if T=="36": return "017-REPRESENTACION  VENTA NAL (CENTRO 730)"
 if D=="DEBITO" and T=="08": return "017-ORIGINAL REEMBOLSOS DEBITO"
 if D=="CREDITO" and T=="08": return "017-ORIGINAL REEMBOLSOS CREDITO"
 if T=="42" and B!="439467" and K not in ("15","16","03") and D in ("CREDITO","DEBITO"): return "017-COMISIONES NO EXITOSAS TD Y TC IMPUTABLES BANCO"
 if T=="42" and B!="439467" and K not in ("05","06","03") and D in ("CREDITO","DEBITO"): return "017-COMISIONES NO EXITOSAS TD Y TC  TIPO 15 Y 16"
 if D=="CREDITO" and T in ("06","02"): return "017-CANJE RECIBIDO TARJETA CREDITO"
 if D=="CREDITO" and T=="04": return "017-CANJE RECIBIDO TARJETA CREDITO PAGOS"
 if D=="CREDITO" and T=="26": return "017-CANJE RECIBIDO TARJETA CREDITO REVERSION VENTAS 26 VLR. TOTAL"
 if D=="CREDITO" and T=="22": return "017-CANJE RECIBIDO TC REVERSION AVANCES 22"
 if D=="CREDITO" and T=="24": return "017-CANJE RECIBIDO TC REVERSION PAGOS 24"
 if D=="EFIPAGO" and T!="Totales" and T!="56": return "017-VISA PAGOS"
 if D=="VISA VALE" and T!="Totales": return "017-CANJE  UTILIZACION VISA VALE"
 if D=="DEBITO" and P!="CNB" and T=="32": return "017-REPRESENTACION  AVANCE NAL  TD (CENTRO 730)"
 if T=="42" and B!="439467" and K=="03" and D in ("CREDITO","DEBITO"): return "017-NOTAS DEBITO CANJE RECIBIDO"
 if T=="44" and B!="439467" and K=="03" and D in ("CREDITO","DEBITO"): return "017-NOTAS CREDITO CANJE RECIBIDO"
 if D=="CREDITO" and T=="12": return "017-TP 12 DEVO AVANCE"
 return ""

def _cuenta_comision(tipo,canal,tx,comision,tii):
 """=IF(DEBITO+no CNB+TX02+COMISION=7450,"...ONLINE",
      IF(CREDITO+ELECTRONICO+TX02+COMISION=7450,"...BATC",
      IF(CREDITO+TX26+TII<>0,"...TII...","")))"""
 if tipo=="DEBITO" and canal!="CNB" and tx=="02" and comision==7450: return "017-COMISIONES EXIT. TARJETA DEBITO ONLINE"
 if tipo=="CREDITO" and canal=="ELECTRONICO" and tx=="02" and comision==7450: return "017-CJE REC VISA NAL VR COM EXIT TC BATC"
 if tipo=="CREDITO" and tx=="26" and tii not in (None,0): return "017-TII RECIBIDA EMISOR VISA OP REVER VENTAS"
 return ""

def _cuenta_880(bin_dest,tipo,canal,tx):
 """=IF(AND(OR(BIN_DEST=462550,BIN_DEST=417704),TIPO="DEBITO",CANAL<>"CNB",OR(TX=02,TX=06)),"...REGALO","")"""
 if bin_dest in ("462550","417704") and tipo=="DEBITO" and canal!="CNB" and tx in ("02","06"):
  return "017-CANJE RECIBIDO TARJETA DEBITO REGALO"
 return ""

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

   row["TX"]=_tx_normalizado(row["TX"])
   row["ESPACIOS"]=_canal(row["TX"],row["XX"])
   row["TIPO"]=_tipo(row["TARJETA"])
   row["VL_INTERC"]=_vl_interc(row["TX"],row["TIPO"],row.pop("VL_INTERC_RAW"))
   row["COMISION_OP_EXITOSAS"]=_comision_op_exitosas(row["TX"],row["BIN_DEST"])
   row["TII_RECIBIDA_EMISOR_VISA_OP_REVER_VENTAS"]=_tii_recibida(row["TIPO"],row["TX"],row["VL_TOTAL"],row["VL_INTERC"])
   row["CUENTA"]=_cuenta(row["COD_ERROR"],row["TIPO"],row["ESPACIOS"],row["TX"],row["BIN_DEST"],row["MOT_COB"])
   row["CUENTAS_COMISIONES"]=_cuenta_comision(row["TIPO"],row["ESPACIOS"],row["TX"],row["COMISION_OP_EXITOSAS"],row["TII_RECIBIDA_EMISOR_VISA_OP_REVER_VENTAS"])
   row["CUENTA_880"]=_cuenta_880(row["BIN_DEST"],row["TIPO"],row["ESPACIOS"],row["TX"])

   for f in NUMERIC_FIELDS:
    if row[f]=="":row[f]=None
   r.records.append(row)
  r.controls.append({"codigo":"TOTAL_REGISTROS","obtenido":len(r.records)}); return r
