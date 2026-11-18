from app.services.fase2.integracion_depo_inc56i import consultar_depo_jornada

class Cursor:
    def __init__(self): self.calls=[]; self.result=None
    def execute(self,sql,params=None):
        self.calls.append((sql,params))
        self.result=[(1140,"PROCESADO","2026-10-21","abc")] if "con_archivo_carga" in sql else [(1140,21)]
    def fetchall(self): return self.result
    def __enter__(self): return self
    def __exit__(self,*args): pass
class Conn:
    def __init__(self): self.cur=Cursor()
    def cursor(self): return self.cur
    def __enter__(self): return self
    def __exit__(self,*args): pass

def test_cobertura_depo_sin_inventar_montos():
    c=Conn(); r=consultar_depo_jornada(1377,lambda:c)
    f=r["filas"][0]
    assert f["movimientos_persistidos"]==0
    assert f["valor_franquicia"] is None and f["diferencia"] is None
    assert f["concepto"]=="DEPO - archivo de jornada"
    assert r["certificado_monetario"] is False
    assert all("READ ONLY" in c.cur.calls[0][0] or "SELECT" in sql for sql,_ in c.cur.calls)

def test_sin_archivo_no_consulta_detalle():
    class Empty(Cursor):
        def execute(self,sql,params=None):
            self.calls.append((sql,params)); self.result=[]
    c=Conn(); c.cur=Empty()
    r=consultar_depo_jornada(1377,lambda:c)
    assert r["estado"]=="SIN_ARCHIVO_DEPO"
    assert len(c.cur.calls)==2
