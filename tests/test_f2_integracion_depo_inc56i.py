from app.services.fase2.integracion_depo_inc56i import consultar_depo_jornada

class Cursor:
    def __init__(self, filas): self.filas = filas; self.sql = ''
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, sql, params=None):
        self.sql += sql
        if params: assert params == (1377,)
    def fetchall(self): return self.filas
class Conn:
    def __init__(self, filas): self.cur = Cursor(filas)
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def cursor(self): return self.cur

def test_depo_presencia_no_certifica():
    conn = Conn([(15,'PROCESADO','2026-10-21','abc')])
    result = consultar_depo_jornada(1377, lambda:conn)
    assert result['filas'][0]['valor_franquicia'] is None
    assert result['filas'][0]['cuenta'] is None
    assert result['certificado_monetario'] is False
    assert 'READ ONLY' in conn.cur.sql

def test_depo_ausente():
    assert consultar_depo_jornada(1377,lambda:Conn([]))['estado']=='SIN_ARCHIVO_DEPO'

def test_jornada_invalida():
    import pytest
    with pytest.raises(ValueError): consultar_depo_jornada(0)
