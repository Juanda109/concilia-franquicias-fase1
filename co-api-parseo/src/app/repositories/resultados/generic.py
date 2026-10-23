TABLES={'HA22': 'CON_HA22_RESULTADO', 'HA26': 'CON_HA26_RESULTADO', 'HA32': 'CON_HA32_RESULTADO', 'CAET': 'CON_CANJE_RESULTADO', 'CANT': 'CON_CANT_RESULTADO', 'DEPO': 'CON_DEPOSITO_RESULTADO', 'CARTA_COMPENSACION': 'CON_CARTA_COMP_RESULTADO', 'PMD': 'CON_PMD_RESULTADO', 'MEP': 'CON_MEP_RESULTADO', 'ISS': 'CON_ISS_RESULTADO'}
# Insumos con tabla padre+detalle (ej. VSS: una pagina/reporte en
# CON_VSS_REPORTE, varias lineas de concepto en CON_VSS_DETALLE via FK).
REPORT_TABLES={'VSS': ('CON_VSS_REPORTE','CON_VSS_DETALLE','ID_VSS_REPORTE')}
class ResultRepository:
 def __init__(self,conn):self.conn=conn
 def insert_records(self,tipo,id_archivo,records,reportes=None,on_progress=None,progress_every=500):
  if tipo in REPORT_TABLES:
   return self._insert_reporte_detalle(tipo,id_archivo,records,reportes or [],on_progress,progress_every)
  table=TABLES.get(tipo)
  if not table:return 0
  self.conn.execute(f"DELETE FROM {table} WHERE ID_ARCHIVO=%s",(id_archivo,))
  count=0
  for rec in records:
   data={k.upper():v for k,v in rec.items() if k!="numero_linea" and not k.startswith("_")}
   cols=["ID_ARCHIVO","NUMERO_LINEA"]+list(data)
   vals=[id_archivo,rec.get("numero_linea")]+list(data.values())
   placeholders=",".join(["%s"]*len(vals))
   self.conn.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})",vals);count+=1
   if on_progress and count%progress_every==0: on_progress(count)
  if on_progress: on_progress(count)
  return count

 def _insert_reporte_detalle(self,tipo,id_archivo,records,reportes,on_progress,progress_every):
  tabla_padre,tabla_hijo,fk_col=REPORT_TABLES[tipo]
  self.conn.execute(f"DELETE FROM {tabla_hijo} WHERE {fk_col} IN (SELECT {fk_col} FROM {tabla_padre} WHERE ID_ARCHIVO=%s)",(id_archivo,))
  self.conn.execute(f"DELETE FROM {tabla_padre} WHERE ID_ARCHIVO=%s",(id_archivo,))
  id_por_key={}
  for rep in reportes:
   data={k.upper():v for k,v in rep.items() if k!="numero_linea" and not k.startswith("_")}
   cols=["ID_ARCHIVO","NUMERO_LINEA"]+list(data)
   vals=[id_archivo,rep.get("numero_linea")]+list(data.values())
   placeholders=",".join(["%s"]*len(vals))
   row=self.conn.execute(f"INSERT INTO {tabla_padre} ({','.join(cols)}) VALUES ({placeholders}) RETURNING {fk_col}",vals).fetchone()
   id_por_key[rep["_key"]]=row[0]
  count=0
  for rec in records:
   data={k.upper():v for k,v in rec.items() if k!="numero_linea" and not k.startswith("_")}
   cols=[fk_col,"NUMERO_LINEA"]+list(data)
   vals=[id_por_key[rec["_report_key"]],rec.get("numero_linea")]+list(data.values())
   placeholders=",".join(["%s"]*len(vals))
   self.conn.execute(f"INSERT INTO {tabla_hijo} ({','.join(cols)}) VALUES ({placeholders})",vals);count+=1
   if on_progress and count%progress_every==0: on_progress(count)
  if on_progress: on_progress(count)
  return count
