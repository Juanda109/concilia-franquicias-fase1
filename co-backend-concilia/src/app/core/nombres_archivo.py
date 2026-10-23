import re
from datetime import date

# Estructura fija por tipo de insumo; lo único que cambia día a día es la
# fecha embebida en el nombre. "formato" indica cómo leer los dígitos de
# fecha capturados por el grupo del regex: 'AAMMDD'/'DDMMAA' (6 dígitos,
# año de 2 cifras), 'AAAAMMDD' (8 dígitos, año ya completo), 'ISO' (el
# grupo ya viene como AAAA-MM-DD, con guiones) o 'DDMES_ES' (dos grupos:
# día + nombre del mes en español, SIN año - el año se toma de la fecha
# contable de la jornada, ver validar_nombre).
# Tipos sin regla aquí (MEP, PMPD1322, PMRD8000) no tienen estructura de
# nombre confirmada todavía: no se valida nada para ellos.
_MESES_ES={'ENERO':1,'FEBRERO':2,'MARZO':3,'ABRIL':4,'MAYO':5,'JUNIO':6,
 'JULIO':7,'AGOSTO':8,'SEPTIEMBRE':9,'OCTUBRE':10,'NOVIEMBRE':11,'DICIEMBRE':12}

PATRONES={
 "HA22":(re.compile(r'^DESCARHA22_F(\d{6})\.TXT$',re.I),'AAMMDD'),
 "HA26":(re.compile(r'^DESCARHA26_F(\d{6})\.TXT$',re.I),'AAMMDD'),
 "HA32":(re.compile(r'^DESCARHA32_F(\d{6})\.TXT$',re.I),'AAMMDD'),
 "CAET":(re.compile(r'^GOF\.MRD0001\.F(\d{6})\.RD001\.CAET\.TXT$',re.I),'AAMMDD'),
 "CANT":(re.compile(r'^GOF\.MRD0001\.RD002\.F(\d{6})\.CANT\s*\.TXT$',re.I),'AAMMDD'),
 "DEPO":(re.compile(r'^GOF\.E0007\.GRMRV05\.F(\d{6})\.RD001\.DEPO\.TXT$',re.I),'AAMMDD'),
 "CARTA_COMPENSACION":(re.compile(r'^(\d{6})\.xlsx$',re.I),'DDMMAA'),
 "PMD":(re.compile(r'^PMDGeneralEntidad(\d{8})\.xls$',re.I),'AAAAMMDD'),
 "ISS":(re.compile(r'^International  SS_Data_(\d{4}-\d{2}-\d{2})\.pdf$',re.I),'ISO'),
 "VSS":(re.compile(r'^VSS BBVA (\d{2}) ([A-Z]+)\.TXT$',re.I),'DDMES_ES'),
}

def _fecha_desde_match(m:re.Match,formato:str,anio_defecto:int)->str|None:
 if formato=='ISO': return m.group(1)
 if formato=='AAAAMMDD':
  digitos=m.group(1); aaaa,mm,dd=digitos[0:4],digitos[4:6],digitos[6:8]
  return f"{aaaa}-{mm}-{dd}"
 if formato=='DDMES_ES':
  dia,mes_nombre=m.group(1),m.group(2).upper()
  mes=_MESES_ES.get(mes_nombre)
  if not mes: return None
  try: return date(anio_defecto,mes,int(dia)).isoformat()
  except ValueError: return None
 digitos=m.group(1)
 if formato=='AAMMDD': aa,mm,dd=digitos[0:2],digitos[2:4],digitos[4:6]
 else: dd,mm,aa=digitos[0:2],digitos[2:4],digitos[4:6]
 return f"20{aa}-{mm}-{dd}"

def validar_nombre(tipo_insumo:str,nombre_archivo:str,fecha_contable_iso:str|None=None):
 """Devuelve (tiene_regla, coincide, fecha_archivo_iso|None).
 tiene_regla=False cuando el tipo todavía no tiene estructura confirmada
 (no se valida nada, igual que antes). tiene_regla=True y coincide=False
 cuando el nombre no cumple la estructura esperada para ese tipo.
 fecha_contable_iso es obligatorio para tipos sin año en el nombre
 (formato 'DDMES_ES', ej. VSS): el año de la fecha extraída se toma de
 ahí (el nombre solo trae día+mes), así que el chequeo de fecha en
 main.py termina comparando únicamente día y mes para esos casos."""
 regla=PATRONES.get(tipo_insumo)
 if not regla: return False,True,None
 patron,formato=regla
 m=patron.match((nombre_archivo or '').strip())
 if not m: return True,False,None
 anio_defecto=int(fecha_contable_iso[0:4]) if fecha_contable_iso else date.today().year
 fecha=_fecha_desde_match(m,formato,anio_defecto)
 if fecha is None: return True,False,None
 return True,True,fecha
