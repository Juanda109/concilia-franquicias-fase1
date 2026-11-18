from decimal import Decimal
import pytest
from app.services.fase2.integracion_depo_inc56i import (
    normalizar_sumifs_host, CUENTAS_DEPO_APROBADAS, consultar_depo_jornada,
)

def test_referencia_cuentas_d2_d5():
    assert CUENTAS_DEPO_APROBADAS == {
        'DEPOSITO_NACIONAL':'196095001838',
        'DEPOSITO_INTERNACIONAL':'196095001839'}
    filas = normalizar_sumifs_host([
        ('HA22','196095001838',Decimal('2910'),Decimal('2912')),
        ('HA22','196095001839',Decimal('2920'),Decimal('2922')),
    ])
    assert [(x['celda_referencia'],x['importe_contable']) for x in filas] == [
        ('D2','2910'),('D3','2912'),('D4','2920'),('D5','2922')]

def test_no_duplica_fuentes():
    filas = normalizar_sumifs_host([
        ('HA22','196095001838','10','12'),
        ('HA26','196095001838','10','12'),
        ('HA32','196095001838','10','12'),
    ])
    assert len(filas)==6
    assert {x['fuente_host'] for x in filas} == {'HA22','HA26','HA32'}
    assert all(x['importe_contable'] in ('10','12') for x in filas)

def test_rechaza_importes_inexactos():
    with pytest.raises(ValueError):
        normalizar_sumifs_host([('HA22','196095001838',1.2,0)])
    with pytest.raises(ValueError):
        normalizar_sumifs_host([('HA22','900000000281','10','0')])

def test_no_certifica_depo_con_mock():
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def execute(self,sql,params=None): pass
        def fetchall(self): return [(1140,'PROCESADO','2026-10-21','sha')]
    class Conn:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def cursor(self): return Cursor()
    r=consultar_depo_jornada(1377,lambda:Conn())
    assert r['certificado_monetario'] is False
    assert r['sumatorias_host_por_fuente']==[]
    assert r['filas'][0]['diferencia'] is None
