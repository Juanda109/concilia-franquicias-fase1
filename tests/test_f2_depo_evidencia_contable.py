from app.services.fase2.integracion_depo_inc56i import construir_evidencia_contable
import pytest


def test_fuente_unica_y_referencias():
    filas = [
        {'fuente_host': f, 'cuenta': c, 'naturaleza': n, 'importe_contable': v}
        for f in ('HA22', 'HA26', 'HA32')
        for c in ('196095001838', '196095001839')
        for n, v in (('D', '2910.00'), ('H', '2912.00'))
    ]
    resultado = construir_evidencia_contable(filas, 'HA22')
    assert len(resultado) == 2
    assert all(r['fuente_host'] == 'HA22' for r in resultado)
    assert resultado[0]['debe_host'] == '2910.00'
    assert resultado[0]['referencia_debe'] == 'D2'
    assert resultado[1]['referencia_haber'] == 'D5'
    assert all(r['valor_franquicia'] is None and r['diferencia'] is None for r in resultado)
    assert all(not r['certificado_monetario'] for r in resultado)


def test_sin_fuente_no_inventa_seleccion():
    assert construir_evidencia_contable([], None) == []


def test_rechaza_fuente_invalida():
    with pytest.raises(ValueError):
        construir_evidencia_contable([], 'HA99')


def test_faltantes_no_se_convierten_en_cero():
    r = construir_evidencia_contable([], 'HA22')
    assert all(x['debe_host'] is None and x['haber_host'] is None for x in r)
