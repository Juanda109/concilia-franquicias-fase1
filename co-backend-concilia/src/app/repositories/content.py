TABLES={
 'HA22':'CON_HA22_RESULTADO','HA26':'CON_HA26_RESULTADO','HA32':'CON_HA32_RESULTADO',
 'CAET':'CON_CANJE_RESULTADO','CANT':'CON_CANJE_RESULTADO','DEPO':'CON_DEPOSITO_RESULTADO',
 'CARTA_COMPENSACION':'CON_CARTA_COMP_RESULTADO','PMD':'CON_PMD_RESULTADO','MEP':'CON_MEP_RESULTADO'
}
class ContentRepository:
    def __init__(self,conn): self.conn=conn
    @staticmethod
    def _rows(cur):
        cols=[d.name for d in cur.description]
        return [dict(zip(cols,row)) for row in cur.fetchall()]
    def page(self,tipo,id_archivo,page=0,size=30):
        if tipo=='VSS':
            cur=self.conn.execute('''SELECT d.* FROM CON_VSS_DETALLE d JOIN CON_VSS_REPORTE r ON r.ID_VSS_REPORTE=d.ID_VSS_REPORTE WHERE r.ID_ARCHIVO=%s ORDER BY d.NUMERO_PAGINA,d.NUMERO_LINEA LIMIT %s OFFSET %s''',(id_archivo,size,page*size))
            rows=self._rows(cur)
            total=self.conn.execute('''SELECT COUNT(*) FROM CON_VSS_DETALLE d JOIN CON_VSS_REPORTE r ON r.ID_VSS_REPORTE=d.ID_VSS_REPORTE WHERE r.ID_ARCHIVO=%s''',(id_archivo,)).fetchone()[0]
            return rows,total
        table=TABLES.get(tipo)
        if not table: raise KeyError(tipo)
        cur=self.conn.execute(f'SELECT * FROM {table} WHERE ID_ARCHIVO=%s ORDER BY NUMERO_LINEA NULLS LAST LIMIT %s OFFSET %s',(id_archivo,size,page*size))
        rows=self._rows(cur)
        total=self.conn.execute(f'SELECT COUNT(*) FROM {table} WHERE ID_ARCHIVO=%s',(id_archivo,)).fetchone()[0]
        return rows,total
