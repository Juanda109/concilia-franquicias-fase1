from unittest.mock import patch
import pytest
from app.services.fase2.diagnostico_host_inc49 import obtener_diagnostico_host

class Cursor:
    def execute(self, sql, params=None):
        assert 'SET TRANSACTION READ ONLY' in sql or 'EXISTS' in sql
    def fetchall(self):
        return [('HA22','299095302','17',2207,1,11747139,0,11747139,[2],['PRUEBA SINTETICA'])]
    def __enter__(self): return self
    def __exit__(self,*args): return False
class Conn:
    def cursor(self): return Cursor()
    def __enter__(self): return self
    def __exit__(self,*args): return False

def test_lectura_no_certificada():
    with patch('app.services.fase2.diagnostico_host_inc49.connection',return_value=Conn()):
        r=obtener_diagnostico_host(2590)
    assert not r['certificado']
    assert r['filas'][0]['evidencia_sintetica_explicita']
    assert r['filas'][0]['neto_diagnostico']=='11747139'
    assert 'total_host' not in r['filas'][0]

@pytest.mark.parametrize('jornada',[0,-1,'2590'])
def test_jornada_invalida(jornada):
    with pytest.raises(ValueError): obtener_diagnostico_host(jornada)
