from contextlib import contextmanager
import pytest
from app.services.fase2.lectura_jornada_pg_inc39 import leer_jornada
from app.services.fase2.contrato_maestro_inc39 import validar_fila, contrato_vacio, COLUMNAS
class Cursor:
    def __init__(self,rows): self.rows=iter(rows); self.calls=[]
    def __enter__(self): return self
    def __exit__(self,*a): return False
    def execute(self,sql,params=None): self.calls.append((sql,params))
    def fetchone(self): return next(self.rows)
    def fetchall(self): return next(self.rows)
class Conn:
    def __init__(self,rows): self.cur=Cursor(rows)
    def __enter__(self): return self
    def __exit__(self,*a): return False
    def cursor(self,**kw): return self.cur
def conectar(rows):
    @contextmanager
    def f(): yield Conn(rows)
    return f
def test_jornada_vacia():
    d=leer_jornada(1377,conectar([{'id_jornada':1377,'fecha_contable':'2026-10-21','estado':'PENDIENTE'},[]]))
    assert d['archivos']==[] and d['cruces']==[] and d['certificado'] is False
def test_conteos_sin_inventar_importes():
    a={'id_archivo':1254,'tipo_archivo':'CANT','estado':'PROCESADO','fecha_contable':'2026-10-21','checksum_sha256':'abc','correlation_id':'x'}
    d=leer_jornada(1377,conectar([{'id_jornada':1377,'fecha_contable':'2026-10-21','estado':'PENDIENTE'},[a],{'n':4}]))
    assert d['archivos'][0]['registros_detalle']==4
    assert d['archivos'][0]['valor'] is None
    assert d['archivos'][0]['franquicia']=='CREDIBANCO'
def test_fecha_distinta_bloquea():
    a={'id_archivo':1254,'tipo_archivo':'CANT','estado':'PROCESADO','fecha_contable':'2026-10-22','checksum_sha256':None,'correlation_id':None}
    d=leer_jornada(1377,conectar([{'id_jornada':1377,'fecha_contable':'2026-10-21','estado':'PENDIENTE'},[a],{'n':2}]))
    assert d['archivos'][0]['estado']=='FECHA_INCONSISTENTE'
@pytest.mark.parametrize('id_', [0,-1,True,'1377'])
def test_id_invalido(id_):
    with pytest.raises(ValueError): leer_jornada(id_,lambda:None)
def test_jornada_inexistente():
    with pytest.raises(ValueError): leer_jornada(10,conectar([None]))
def test_contrato_11_columnas():
    assert len(COLUMNAS)==11 and contrato_vacio()['filas']==[]
def test_no_franquicia_host():
    f={c:None for c in COLUMNAS}; f.update(franquicia='HOST',estado_conciliacion='PENDIENTE_F2')
    with pytest.raises(ValueError): validar_fila(f)
def test_no_cruce_ficticio():
    f={c:None for c in COLUMNAS}; f.update(franquicia='CREDIBANCO',estado_conciliacion='PENDIENTE_HOMOLOGACION',diferencia='0')
    with pytest.raises(ValueError): validar_fila(f)
