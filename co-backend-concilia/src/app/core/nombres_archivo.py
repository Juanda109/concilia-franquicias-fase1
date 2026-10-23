import re

# Estructura fija por tipo de insumo; lo único que cambia día a día es la
# fecha embebida en el nombre. "formato" indica cómo leer los dígitos de
# fecha capturados por el grupo del regex: 'AAMMDD'/'DDMMAA' (6 dígitos,
# año de 2 cifras), 'AAAAMMDD' (8 dígitos, año ya completo) o 'ISO' (el
# grupo ya viene como AAAA-MM-DD, con guiones, no hace falta reordenar).
# Tipos sin regla aquí (MEP, VSS, PMPD1322, PMRD8000) no tienen estructura
# de nombre confirmada todavía: no se valida nada para ellos.
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
}

def _fecha_desde_digitos(digitos:str,formato:str)->str:
 if formato=='ISO': return digitos
 if formato=='AAAAMMDD':
  aaaa,mm,dd=digitos[0:4],digitos[4:6],digitos[6:8]
  return f"{aaaa}-{mm}-{dd}"
 if formato=='AAMMDD': aa,mm,dd=digitos[0:2],digitos[2:4],digitos[4:6]
 else: dd,mm,aa=digitos[0:2],digitos[2:4],digitos[4:6]
 return f"20{aa}-{mm}-{dd}"

def validar_nombre(tipo_insumo:str,nombre_archivo:str):
 """Devuelve (tiene_regla, coincide, fecha_archivo_iso|None).
 tiene_regla=False cuando el tipo todavía no tiene estructura confirmada
 (no se valida nada, igual que antes). tiene_regla=True y coincide=False
 cuando el nombre no cumple la estructura esperada para ese tipo."""
 regla=PATRONES.get(tipo_insumo)
 if not regla: return False,True,None
 patron,formato=regla
 m=patron.match((nombre_archivo or '').strip())
 if not m: return True,False,None
 return True,True,_fecha_desde_digitos(m.group(1),formato)
