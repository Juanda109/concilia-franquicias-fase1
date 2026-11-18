import pytest
from app.services.fase2.excepcionales_redeban_inc65 import evaluar

@pytest.mark.parametrize('fila,indices', [(1371,(4,9)),(1640,(4,10)),(3110,(5,10)),(3111,(5,10))])
def test_formulas(fila,indices):
    r = ['COD'] + [0]*11
    r[indices[0]-1] = '100.25'
    r[indices[1]-1] = '20.10'
    resultado = evaluar(fila,'COD','196095001090','SHA',[r])
    assert resultado['neto_diagnostico'] == '80.15'
    assert resultado['certificado'] is False

def test_ausente_no_es_cero():
    r = evaluar(1371,'COD','1','SHA',[])
    assert r['neto_diagnostico'] is None
    assert r['estado'] == 'OPERANDOS_NO_RESUELTOS'

def test_duplicado_no_se_elije_arbitrariamente():
    row=['COD']+[0]*11
    r=evaluar(1371,'COD','1','SHA',[row,row])
    assert r['estado']=='CODIGO_PMD_DUPLICADO'

def test_celda_vacia_no_es_cero():
    row=['COD']+[0]*11
    row[3]=None
    r=evaluar(1371,'COD','1','SHA',[row])
    assert r['neto_diagnostico'] is None

def test_rechaza_nan():
    row=['COD']+[0]*11
    row[3]='NaN'
    with pytest.raises(ValueError):
        evaluar(1371,'COD','1','SHA',[row])

def test_rechaza_fila_incorrecta():
    with pytest.raises(ValueError):
        evaluar(100,'COD','1','SHA',[])
