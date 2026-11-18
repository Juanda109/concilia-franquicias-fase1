import json
from pathlib import Path
import pytest
from app.services.fase2.formulas_credibanco_inc45 import ejecutar, verificar_catalogo, EvidenciaInsuficiente

CAT = json.loads((Path(__file__).resolve().parents[1] / 'catalogo_credibanco_inc44.json').read_text(encoding='utf-8'))

def test_catalogo_seis_formulas():
    assert len(verificar_catalogo(CAT)) == 6

def test_busquedas_columna_b_c_y_f90():
    filas = [{'A':r['concepto'], 'B':'12.50', 'C':'21.75'} for r in CAT['reglas']]
    res = ejecutar(CAT, filas, f90='2.50')['resultados']
    assert [r['valor'] for r in res] == ['12.50','21.75','12.50','21.75','12.50','10.00']

def test_no_encontrado_devuelve_cero_marcado():
    res = ejecutar(CAT, [])['resultados']
    assert all(r['estado'] == 'CERO_POR_NO_ENCONTRADO_EXCEL' and r['valor'] == '0' for r in res)

def test_nulo_no_es_cero():
    r = CAT['reglas'][0]
    res = ejecutar(CAT,[{'A':r['concepto'],'B':None,'C':'4'}])['resultados'][0]
    assert res['estado']=='PENDIENTE_DATO' and res['valor'] is None

def test_f90_faltante_no_inventado():
    r = next(x for x in CAT['reglas'] if x['fila']==92)
    res = ejecutar(CAT,[{'A':r['concepto'],'B':'10'}])['resultados'][-1]
    assert res['estado']=='PENDIENTE_DATO'

def test_duplicados_primera_coincidencia():
    r=CAT['reglas'][0]
    rows=[{'A':r['concepto'],'B':'2'}, {'A':r['concepto'],'B':'99'}]
    v=ejecutar(CAT,rows)['resultados'][0]
    assert v['valor']=='2' and v['coincidencias']==2 and 'advertencia' in v

def test_cero_real_se_distingue():
    r=CAT['reglas'][0]
    v=ejecutar(CAT,[{'A':r['concepto'],'B':'0'}])['resultados'][0]
    assert v['valor']=='0' and v['estado']=='CALCULADO_DESDE_TOTALES_NO_HOMOLOGADO'

def test_rechaza_no_finito():
    r=CAT['reglas'][0]
    v=ejecutar(CAT,[{'A':r['concepto'],'B':'NaN'}])['resultados'][0]
    assert v['estado']=='PENDIENTE_DATO'

def test_no_certifica():
    assert ejecutar(CAT,[])['certificado'] is False

def test_catalogo_incompleto():
    with pytest.raises(EvidenciaInsuficiente):
        verificar_catalogo({'reglas':CAT['reglas'][:-1]})
