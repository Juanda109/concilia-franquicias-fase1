import pytest
from datetime import date
from app.services.fase2.cobertura_contable_inc55 import CoberturaContable, transicionar, evaluar_cobertura

def base(**kw):
    d=dict(fecha=date(2026,11,2), fuente='HA22', cuenta='299095302', centro='0017', tipo_consulta='MOVIMIENTOS')
    d.update(kw)
    return CoberturaContable(**d)

def test_procesado_no_confirma():
    c=transicionar(transicionar(base(), 'EN_PROCESO'), 'PROCESADO')
    assert c.estado=='PROCESADO'
    assert evaluar_cobertura([c])['confirmados']==0

def test_confirmacion_requiere_evidencia():
    c=transicionar(transicionar(base(), 'EN_PROCESO'), 'PROCESADO')
    with pytest.raises(ValueError): transicionar(c,'CONFIRMADO')
    assert transicionar(c,'CONFIRMADO',evidencia_cierre='CIERRE-VALIDADO').estado=='CONFIRMADO'

def test_reintento_sin_maximo():
    c=base()
    for _ in range(15):
        c=transicionar(transicionar(c,'EN_PROCESO'),'FALLIDO')
    assert transicionar(c,'EN_PROCESO').estado=='EN_PROCESO'

def test_referencia_obligatoria():
    with pytest.raises(ValueError): base(tipo_consulta='SALDO_REFERENCIA')

def test_contradicciones_bloqueadas():
    with pytest.raises(ValueError): evaluar_cobertura([base(),base(estado='FALLIDO')])

def test_clave_por_fuente_y_tipo():
    assert evaluar_cobertura([base(),base(fuente='HA26'),base(tipo_consulta='SALDO_CIERRE')])['total']==3

def test_confirmacion_directa_bloqueada():
    with pytest.raises(ValueError): transicionar(base(),'CONFIRMADO',evidencia_cierre='x')
