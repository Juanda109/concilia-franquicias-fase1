from decimal import Decimal
from app.services.fase2.auditoria_operandos_redeban import auditar


def test_agrupa_causas_y_no_inventa_ceros():
    filas = [
        {'cuenta_contable':'123', 'estado':'OPERANDOS_NO_RESUELTOS', 'fila_excel':8,
         'codigo_operacion':'1.1', 'calculo':{'debito':{'estado':'SIN_COINCIDENCIA'},
                                           'credito':{'estado':'ENCONTRADO','valor':'0'}}},
        {'cuenta_contable':'123', 'estado':'CALCULO_DIAGNOSTICO', 'neto_diagnostico':'1.25'},
        {'cuenta_contable':'999', 'estado':'PARTIDA_MANUAL_NO_HOMOLOGADA'}]
    r = auditar(filas, {'123'})
    assert r['total_filas'] == 3
    assert r['cuentas']['123']['causas'] == {'DEBITO:SIN_COINCIDENCIA': 1}
    assert r['cuentas']['123']['neto_parcial_no_conciliable'] == '1.25'
    assert r['certificado'] is False


def test_sin_calculos_es_none():
    r = auditar([{'cuenta_contable':'123','estado':'OPERANDOS_NO_RESUELTOS'}], {'123'})
    assert r['cuentas']['123']['neto_parcial_no_conciliable'] is None


def test_rechaza_float_y_nan():
    import pytest
    for valor in [1.2, 'NaN', None]:
        with pytest.raises(ValueError):
            auditar([{'cuenta_contable':'123','estado':'CALCULO_DIAGNOSTICO',
                     'neto_diagnostico':valor}], {'123'})


def test_no_muta_entrada():
    filas = [{'cuenta_contable':'123','estado':'OPERANDOS_NO_RESUELTOS'}]
    original = [dict(filas[0])]
    auditar(filas, {'123'})
    assert filas == original
