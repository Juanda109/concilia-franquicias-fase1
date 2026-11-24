import re
from datetime import date, timedelta

# Estructura fija por tipo de insumo; lo único que cambia día a día es la
# fecha embebida en el nombre. Un tipo puede aceptar varias estructuras
# (se prueban en orden). "formato" indica cómo leer los dígitos de fecha
# capturados por el regex: 'AAMMDD'/'DDMMAA' (6 dígitos, año de 2 cifras),
# 'AAAAMMDD' (8 dígitos, año completo), 'ISO' (el grupo ya viene como
# AAAA-MM-DD), 'DDMES_ES' (día + nombre completo del mes en español, SIN
# año: el año se toma de la fecha contable de la jornada, ver
# validar_nombre) o 'DDMMMAA' (día + mes abreviado en español o inglés +
# año de 2 cifras, ej. 10NOV26).
# Tipos sin regla aquí (MEP, PMPD1322, PMRD8000) no tienen estructura de
# nombre confirmada todavía: no se valida nada para ellos.
_MESES_ES={'ENERO':1,'FEBRERO':2,'MARZO':3,'ABRIL':4,'MAYO':5,'JUNIO':6,
 'JULIO':7,'AGOSTO':8,'SEPTIEMBRE':9,'OCTUBRE':10,'NOVIEMBRE':11,'DICIEMBRE':12}
_MESES_ABREV={'ENE':1,'JAN':1,'FEB':2,'MAR':3,'ABR':4,'APR':4,'MAY':5,'JUN':6,'JUL':7,
 'AGO':8,'AUG':8,'SEP':9,'SET':9,'OCT':10,'NOV':11,'DIC':12,'DEC':12}

# (regex, formato, descripción legible del formato esperado)
PATRONES={
 "HA22":[(re.compile(r'^DESCARHA22_F(\d{6})\.TXT$',re.I),'AAMMDD','DESCARHA22_FAAMMDD.TXT (ej. DESCARHA22_F261110.TXT)')],
 "HA26":[(re.compile(r'^DESCARHA26_F(\d{6})\.TXT$',re.I),'AAMMDD','DESCARHA26_FAAMMDD.TXT (ej. DESCARHA26_F261110.TXT)')],
 "HA32":[(re.compile(r'^DESCARHA32_F(\d{6})\.TXT$',re.I),'AAMMDD','DESCARHA32_FAAMMDD.TXT (ej. DESCARHA32_F261110.TXT)')],
 "CAET":[(re.compile(r'^GOF\.MRD0001\.F(\d{6})\.RD001\.CAET\.TXT$',re.I),'AAMMDD',
          'GOF.MRD0001.FAAMMDD.RD001.CAET.TXT (ej. GOF.MRD0001.F261110.RD001.CAET.TXT)')],
 "CANT":[(re.compile(r'^GOF\.MRD0001\.RD002\.F(\d{6})\.CANT\s*\.TXT$',re.I),'AAMMDD',
          'GOF.MRD0001.RD002.FAAMMDD.CANT.TXT (ej. GOF.MRD0001.RD002.F261110.CANT.TXT)')],
 "DEPO":[(re.compile(r'^GOF\.E0007\.GRMRV05\.F(\d{6})\.RD001\.DEPO\.TXT$',re.I),'AAMMDD',
          'GOF.E0007.GRMRV05.FAAMMDD.RD001.DEPO.TXT (ej. GOF.E0007.GRMRV05.F261110.RD001.DEPO.TXT)')],
 "CARTA_COMPENSACION":[(re.compile(r'^(\d{6})\.xlsx$',re.I),'DDMMAA','DDMMAA.xlsx (ej. 101126.xlsx)')],
 "PMD":[(re.compile(r'^PMDGeneralEntidad(\d{8})\.xls$',re.I),'AAAAMMDD',
         'PMDGeneralEntidadAAAAMMDD.xls (ej. PMDGeneralEntidad20261110.xls)')],
 # Uno o más espacios entre "International" y "SS": la muestra original traía
 # dos, pero también llegan con uno.
 "ISS":[(re.compile(r'^International\s+SS_Data_(\d{4}-\d{2}-\d{2})\.pdf$',re.I),'ISO',
         'International SS_Data_AAAA-MM-DD.pdf (ej. International SS_Data_2026-11-10.pdf)')],
 # El dia puede venir con uno o dos digitos ("VSS BBVA 9 NOVIEMBRE.txt",
 # "VSS BBVA 09NOV26.txt").
 "VSS":[(re.compile(r'^VSS BBVA (\d{1,2})([A-Z]{3})(\d{2})\.TXT$',re.I),'DDMMMAA',
         'VSS BBVA DDMMMAA.txt (ej. VSS BBVA 10NOV26.txt o VSS BBVA 9NOV26.txt)'),
        (re.compile(r'^VSS BBVA (\d{1,2}) ([A-Z]+)\.TXT$',re.I),'DDMES_ES',
         'VSS BBVA DD MES.txt, con el mes completo en español (ej. VSS BBVA 10 NOVIEMBRE.txt o VSS BBVA 9 NOVIEMBRE.txt)')],
}

# Insumos cuyo archivo trae la fecha del dia anterior a la fecha contable de
# la jornada (dia calendario): para la jornada del 11/11 llega
# PMDGeneralEntidad20261110.xls y VSS BBVA 10NOV26.txt. Los demas tipos traen
# la misma fecha de la jornada.
DESFASE_DIAS={"PMD":1,"VSS":1}

def fecha_esperada_archivo(tipo_insumo:str,fecha_contable_iso:str)->str:
 """Fecha que debe traer el nombre del archivo para la jornada dada."""
 dias=DESFASE_DIAS.get(tipo_insumo,0)
 if not dias: return fecha_contable_iso
 return (date.fromisoformat(fecha_contable_iso)-timedelta(days=dias)).isoformat()

def formato_esperado(tipo_insumo:str)->str|None:
 """Texto con las estructuras aceptadas para el tipo, para mostrar al usuario."""
 reglas=PATRONES.get(tipo_insumo)
 if not reglas: return None
 return ' o '.join(desc for _,_,desc in reglas)

def _fecha_desde_match(m:re.Match,formato:str,anio_defecto:int)->str|None:
 if formato=='ISO': return m.group(1)
 if formato=='AAAAMMDD':
  digitos=m.group(1); aaaa,mm,dd=digitos[0:4],digitos[4:6],digitos[6:8]
  return f"{aaaa}-{mm}-{dd}"
 if formato in ('DDMES_ES','DDMMMAA'):
  dia=int(m.group(1))
  if formato=='DDMES_ES': mes,anio=_MESES_ES.get(m.group(2).upper()),anio_defecto
  else: mes,anio=_MESES_ABREV.get(m.group(2).upper()),2000+int(m.group(3))
  if not mes: return None
  try: return date(anio,mes,dia).isoformat()
  except ValueError: return None
 digitos=m.group(1)
 if formato=='AAMMDD': aa,mm,dd=digitos[0:2],digitos[2:4],digitos[4:6]
 else: dd,mm,aa=digitos[0:2],digitos[2:4],digitos[4:6]
 return f"20{aa}-{mm}-{dd}"

def validar_nombre(tipo_insumo:str,nombre_archivo:str,fecha_contable_iso:str|None=None):
 """Devuelve (tiene_regla, coincide, fecha_archivo_iso|None).
 tiene_regla=False cuando el tipo todavía no tiene estructura confirmada
 (no se valida nada, igual que antes). tiene_regla=True y coincide=False
 cuando el nombre no cumple ninguna estructura esperada para ese tipo.
 fecha_contable_iso se usa para tipos sin año en el nombre (formato
 'DDMES_ES', ej. "VSS BBVA 10 NOVIEMBRE.txt"): el año se toma de ahí, así
 que el chequeo de fecha en main.py compara solo día y mes. Con 'DDMMMAA'
 (ej. "VSS BBVA 10NOV26.txt") el año viene en el nombre y se compara la
 fecha completa."""
 reglas=PATRONES.get(tipo_insumo)
 if not reglas: return False,True,None
 nombre=(nombre_archivo or '').strip()
 anio_defecto=int(fecha_contable_iso[0:4]) if fecha_contable_iso else date.today().year
 for patron,formato,_ in reglas:
  m=patron.match(nombre)
  if not m: continue
  fecha=_fecha_desde_match(m,formato,anio_defecto)
  if fecha is not None: return True,True,fecha
 return True,False,None
