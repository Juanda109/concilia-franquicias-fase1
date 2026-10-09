TABLES={
 'HA22':'CON_HA22_RESULTADO','HA26':'CON_HA26_RESULTADO','HA32':'CON_HA32_RESULTADO',
 'CAET':'CON_CANJE_RESULTADO','CANT':'CON_CANT_RESULTADO','DEPO':'CON_DEPOSITO_RESULTADO',
 'CARTA_COMPENSACION':'CON_CARTA_COMP_RESULTADO','PMD':'CON_PMD_RESULTADO','MEP':'CON_MEP_RESULTADO'
}

HEADER_OVERRIDES={'NUMERO_LINEA':'Número Línea'}

def _label(col_upper):
 return HEADER_OVERRIDES.get(col_upper,col_upper.replace('_',' ').title())

def _headers(cols):
 """Columnas visibles para el frontend: se excluyen las internas de
 bookkeeping (cualquier ID_* -llave propia o foránea- y FECHA_CREACION),
 nunca columnas funcionales del parser. Postgres devuelve los nombres en
 minúscula (identificadores sin comillas); se exponen en MAYÚSCULA para
 conservar el nombre funcional/origen tal como lo escribe el parser."""
 visibles=[c for c in cols if c.upper()!='FECHA_CREACION' and not c.upper().startswith('ID_')]
 return visibles,[{'key':c.upper(),'label':_label(c.upper())} for c in visibles]

class ContentRepository:
    def __init__(self,conn): self.conn=conn
    @staticmethod
    def _rows(cur,cols,visibles):
        return [{c.upper():dict(zip(cols,row))[c] for c in visibles} for row in cur.fetchall()]
    def page(self,tipo,id_archivo,page=0,size=30):
        if tipo=='VSS':
            cur=self.conn.execute('''SELECT d.* FROM CON_VSS_DETALLE d JOIN CON_VSS_REPORTE r ON r.ID_VSS_REPORTE=d.ID_VSS_REPORTE WHERE r.ID_ARCHIVO=%s ORDER BY d.NUMERO_PAGINA,d.NUMERO_LINEA LIMIT %s OFFSET %s''',(id_archivo,size,page*size))
            all_cols=[c.name for c in cur.description]
            visibles,headers=_headers(all_cols)
            rows=self._rows(cur,all_cols,visibles)
            total=self.conn.execute('''SELECT COUNT(*) FROM CON_VSS_DETALLE d JOIN CON_VSS_REPORTE r ON r.ID_VSS_REPORTE=d.ID_VSS_REPORTE WHERE r.ID_ARCHIVO=%s''',(id_archivo,)).fetchone()[0]
            return rows,total,headers
        table=TABLES.get(tipo)
        if not table: raise KeyError(tipo)
        cur=self.conn.execute(f'SELECT * FROM {table} WHERE ID_ARCHIVO=%s ORDER BY NUMERO_LINEA NULLS LAST LIMIT %s OFFSET %s',(id_archivo,size,page*size))
        all_cols=[c.name for c in cur.description]
        visibles,headers=_headers(all_cols)
        rows=self._rows(cur,all_cols,visibles)
        total=self.conn.execute(f'SELECT COUNT(*) FROM {table} WHERE ID_ARCHIVO=%s',(id_archivo,)).fetchone()[0]
        return rows,total,headers
