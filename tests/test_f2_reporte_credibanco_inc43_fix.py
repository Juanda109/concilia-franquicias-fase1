from copy import deepcopy
import pytest
from app.services.fase2.reporte_credibanco_inc43 import construir


def base():
    def grupo(familia, concepto):
        return dict(id_jornada=1377, id_archivo=1254, franquicia='CREDIBANCO',
                    insumo='CANT', familia=familia, concepto_literal=concepto,
                    importes={'vl_interc': '25.0000', 'vl_total': '30.0000', 'tii': None},
                    nulos_familia={'tii': 1}, lineas_origen=[31, 32], certificado=False)
    return dict(id_jornada=1377, origen='POSTGRESQL_SOLO_LECTURA', certificado=False,
                resultados=[grupo('principal', 'CONCEPTO'), grupo('cuenta_880', '')])


def test_preserva_importes_diagnosticos_sin_asignacion():
    resultado = construir(base())
    fila, detalle = resultado['filas'][0], resultado['detalle'][0]
    assert fila['cuenta'] is None and fila['valor_franquicia'] is None
    assert detalle['importes_diagnosticos'] == {'vl_interc':'25.0000','vl_total':'30.0000','tii':None}
    assert detalle['nulos_familia']['tii'] == 1
    assert detalle['fuente_importes'] == 'INC41_POSTGRESQL_SOLO_LECTURA'
    assert detalle['lineas_origen'] == [31, 32]


def test_auxiliar_no_se_suma_ni_crea_fila():
    resultado = construir(base())
    assert len(resultado['filas']) == 1
    assert resultado['detalle'][1]['uso'] == 'SOLO_TRAZABILIDAD_NO_SUMAR'
    assert resultado['detalle'][1]['importes_diagnosticos']['vl_interc'] == '25.0000'


def test_preserva_cero_y_nulo():
    datos=base()
    datos['resultados'][0]['importes']['vl_interc']='0'
    datos['resultados'][0]['importes']['vl_total']=None
    detalle=construir(datos)['detalle'][0]['importes_diagnosticos']
    assert detalle['vl_interc']=='0' and detalle['vl_total'] is None


def test_no_modifica_entrada():
    datos=base(); copia=deepcopy(datos)
    construir(datos)
    assert datos == copia


def test_no_certifica_host_ni_cruces():
    resultado=construir(base())
    assert resultado['certificado'] is False
    assert all(v == 0 for v in resultado['indicadores'].values())
    assert all(resultado['filas'][0][c] is None for c in ('ha22','ha26','ha32','total_host','diferencia'))


def test_rechaza_grupo_origen_duplicado():
    datos=base();datos['resultados'].append(deepcopy(datos['resultados'][0]))
    with pytest.raises(ValueError, match='duplicado'): construir(datos)


def test_rechaza_importes_invalidos():
    datos=base();datos['resultados'][0]['importes']=['25']
    with pytest.raises(ValueError, match='invalidos'): construir(datos)
