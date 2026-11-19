from decimal import Decimal
import pytest
from app.services.fase2.motor_liquidacion_visa import (
    ErrorLiquidacionVisa, MovimientoVSS, liquidar_vss110, importe,
)


def muestra():
    return {
        'interchange': MovimientoVSS.desde_valores('370672.69', '223.56'),
        'reimbursement_fees': MovimientoVSS.desde_valores('4.25', '6940.84'),
        'visa_charges': MovimientoVSS.desde_valores('0.00', '0.00'),
    }


def calcular(**cambios):
    args = dict(entidad='1000804671', moneda='USD', conceptos=muestra(),
                credito_total='370676.94', debito_total='7164.40')
    args.update(cambios)
    return liquidar_vss110(**args)


def test_cuatro_reglas_documentales():
    r = calcular()
    assert [x['neto'] for x in r['reglas']] == ['370449.13', '-6936.59', '0.00']
    assert [x['signo'] for x in r['reglas']] == ['CR', 'DB', 'CERO']
    assert r['total'] == {'id': 'VISA-VSS-004', 'credito': '370676.94',
                          'debito': '7164.40', 'neto': '363512.54', 'signo': 'CR'}
    assert r['certificado'] is False and r['conciliado_host'] is False

@pytest.mark.parametrize('credito,debito,neto,signo', [
    ('0', '0', Decimal('0.00'), 'CERO'),
    ('0', '223.56', Decimal('-223.56'), 'DB'),
    ('15.52', '0', Decimal('15.52'), 'CR'),
    ('100', '125', Decimal('-25.00'), 'DB'),
])
def test_signos(credito, debito, neto, signo):
    m = MovimientoVSS.desde_valores(credito, debito)
    assert m.neto == neto and m.signo == signo

@pytest.mark.parametrize('valor', ['NaN', 'Infinity', '1.001', '-1', 'abc', '1,000.00', 1.2, True])
def test_rechaza_importes_invalidos(valor):
    with pytest.raises(ErrorLiquidacionVisa):
        importe(valor)

@pytest.mark.parametrize('cambios', [
    {'moneda': 'COP'}, {'entidad': ''}, {'credito_total': '370676.95'},
    {'debito_total': None}, {'conceptos': {}},
])
def test_rechaza_inconsistencias(cambios):
    with pytest.raises(ErrorLiquidacionVisa):
        calcular(**cambios)


def test_no_modifica_operandos():
    m = muestra()
    calcular(conceptos=m)
    assert m['interchange'].credito == Decimal('370672.69')
