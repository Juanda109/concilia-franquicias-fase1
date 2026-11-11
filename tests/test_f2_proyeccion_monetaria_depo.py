import pytest
from app.services.fase2.proyeccion_monetaria_depo import proyectar_depo


def test_cnb_no_se_asigna_a_cuentas():
    data = proyectar_depo([{'concepto':'017-OP CNBS','cantidad':4,'valor_total_crudo':'219898','lineas_origen':[]}], [])
    assert data['categorias'][0]['cuenta_referencia'] is None
    assert data['categorias'][0]['valor_franquicia_certificado'] is None
    assert data['certificado_monetario'] is False


def test_host_separado_por_fuente():
    host = [{'fuente_host':'HA22','cuenta':'196095001838','naturaleza':'D','importe_contable':'501234.00'}]
    data = proyectar_depo([], host)
    assert data['evidencia_host'][0]['debe'] == '501234.00'
    assert data['evidencia_host'][2]['debe'] is None


def test_calculo_explicito_sin_certificar():
    concepto = '017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS'
    aprobacion = {'version':'PRUEBA-R1','escala':'100', 'regla_neto':'DEBE_MENOS_HABER',
                  'conceptos': {concepto:{'cuenta':'196095001838','naturaleza':'D'}}}
    data = proyectar_depo([{'concepto':concepto,'cantidad':1,'valor_total_crudo':'12345'}], [], aprobacion=aprobacion)
    assert data['categorias'][0]['importe_calculado_no_certificado'] == '123.45'
    assert data['categorias'][0]['valor_franquicia_certificado'] is None


def test_rechaza_correspondencia_incorrecta():
    concepto = '017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS'
    with pytest.raises(ValueError):
        proyectar_depo([{'concepto':concepto,'cantidad':1,'valor_total_crudo':'100'}], [],
        aprobacion={'version':'R1','escala':'100','regla_neto':'DEBE_MENOS_HABER',
                    'conceptos':{concepto:{'cuenta':'196095001839','naturaleza':'D'}}})
