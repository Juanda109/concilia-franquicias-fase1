TABLES={'HA22': 'CON_HA22_RESULTADO', 'HA26': 'CON_HA26_RESULTADO', 'HA32': 'CON_HA32_RESULTADO', 'CAET': 'CON_CANJE_RESULTADO', 'CANT': 'CON_CANJE_RESULTADO', 'DEPO': 'CON_DEPOSITO_RESULTADO', 'CARTA_COMPENSACION': 'CON_CARTA_COMP_RESULTADO', 'PMD': 'CON_PMD_RESULTADO', 'MEP': 'CON_MEP_RESULTADO'}
class ResultRepository:
 def __init__(self,conn):self.conn=conn
 def insert_records(self,tipo,id_archivo,records):
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
  return count
