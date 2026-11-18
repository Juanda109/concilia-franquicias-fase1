import pytest
from decimal import Decimal
from app.services.fase2.motor_monetario_depo_inc56g import agregar


def fila(linea, concepto='DEPOSITO_NACIONAL', importe='100'):
    return dict(archivo_origen='DEPO.txt', linea_origen=linea,
                concepto_verificado=concepto, clasificacion_aprobada=True,
                importe_crudo=importe)


def test_sin_escala_no_publica_importes():
    r = agregar([fila(2)])
    assert r['resultados'][0]['importe_calculado'] is None
    assert r['valor_franquicia'] is None
    assert r['certificado_monetario'] is False


def test_escala_explicita_no_certifica_excel():
    r = agregar([fila(2), fila(3, importe='250')], escala_aprobada='100', regla_version='PRUEBA')
    assert r['resultados'][0]['importe_calculado'] == '3.5'
    assert r['resultados'][0]['cantidad'] == 2
    assert r['resultados'][0]['debe'] is None


def test_no_infiere_clasificacion():
    r = agregar([dict(fila(2), clasificacion_aprobada=False)])
    assert not r['resultados'] and len(r['pendientes']) == 1


def test_rechaza_duplicados():
    with pytest.raises(ValueError, match='duplicado'):
        agregar([fila(2), fila(2)])


def test_rechaza_flotantes_y_escala_sin_version():
    with pytest.raises(ValueError):
        agregar([fila(2, importe=1.1)])
    with pytest.raises(ValueError):
        agregar([fila(2)], escala_aprobada='100')


def test_separa_conceptos_sin_asignar_cuenta():
    r = agregar([fila(2), fila(3, 'REVERSION_NACIONAL', '50')])
    assert len(r['resultados']) == 2
    assert all(x['cuenta'] is None and x['diferencia'] is None for x in r['resultados'])
