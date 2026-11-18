"""Pruebas puras de diagnostico DEPO. No requieren BD ni Excel."""
from decimal import Decimal
from app.services.fase2.cierre_credibanco_v67 import agrupar_depo


def fila(**cambios):
    r = dict(id_archivo=2210, fecha_contable='2026-10-23', concepto=None,
             tipo_movimiento='02', cod_oficina=None, indicador_cash_back='010',
             amex_nacional=None, cantidad=4, valores_invalidos=0,
             valor_total_crudo=Decimal('219894'), nulos_tasa=0,
             tasa_intercambio_cruda=Decimal('219894'))
    r.update(cambios)
    return r


def test_j2590_cnb_clasificado_sin_reprocesar_f1():
    r = agrupar_depo([fila()], {2210})
    assert len(r) == 1
    a = r[0]
    assert a['concepto'] == '017-OP CNBS'
    assert a['concepto_persistido'] is None
    assert a['indicador_cnb'] == '010'
    assert a['cod_oficina'] is None
    assert a['cantidad'] == 4 and a['valor_total_crudo'] == '219894'
    assert a['cuenta_host_candidata'] is None
    assert a['estado'] == 'CLASIFICADO_CNB_SIN_CUENTA_HOST_HOMOLOGADA'
    assert a['certificado'] is False


def test_cnb_tiene_prioridad_sobre_atm_aunque_oficina_vacia():
    a = agrupar_depo([fila(valor_total_crudo='117471', cantidad=1)], {2210})[0]
    assert a['concepto'] == '017-OP CNBS'
    assert 'ATM' not in a['concepto']
    assert a['cuenta_host_candidata'] is None


def test_06_nacional_es_candidato_sin_certificar():
    a = agrupar_depo([fila(tipo_movimiento='06', indicador_cash_back='000',
                           cod_oficina='0001')], {2210})[0]
    assert a['concepto'] == '017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS'
    assert a['cuenta_host_candidata'] == '196095001838'
    assert a['estado'] == 'PENDIENTE_ESCALA_SIGNO_Y_FUENTE_HOST'
    assert a['certificado'] is False


def test_06_internacional_es_candidato_sin_certificar():
    a = agrupar_depo([fila(tipo_movimiento='06', indicador_cash_back='000',
                           cod_oficina='0090')], {2210})[0]
    assert a['cuenta_host_candidata'] == '196095001839'
    assert a['certificado'] is False


def test_discrepancia_concepto_persistido_bloquea():
    a = agrupar_depo([fila(concepto='017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS')], {2210})[0]
    assert a['estado'] == 'DIVERGENCIA_CONCEPTO_PERSISTIDO_VS_REGLA_AU'
    assert a['cuenta_host_candidata'] is None
    assert a['concepto_persistido'] != a['concepto']


def test_registro_05_control_no_conciliable():
    a = agrupar_depo([fila(tipo_movimiento='05')], {2210})[0]
    assert a['estado'] == 'CONTROL_NO_TRANSACCIONAL'
    assert a['cuenta_host_candidata'] is None


def test_grupo_valor_invalido_no_se_concilia():
    a = agrupar_depo([fila(valor_total_crudo=None, valores_invalidos=4,
                           tasa_intercambio_cruda=None, nulos_tasa=4)], {2210})[0]
    assert a['estado'] == 'PENDIENTE_DATOS_ORIGEN'
    assert a['certificado'] is False


def test_registro_origen_de_otra_jornada_no_se_incluye():
    assert agrupar_depo([fila()], {99}) == []
