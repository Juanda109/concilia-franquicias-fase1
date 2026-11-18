from pathlib import Path
import pytest
from app.services.fase2.orquestador_depo_inc56h import conciliar_depo


def test_extrae_campos_sin_excel(tmp_path):
    archivo = tmp_path / 'depo.txt'
    linea = list('0'*282)
    linea[:2] = '06'
    linea[122:131] = '000050000'
    linea[245:254] = '000048530'
    linea[264:267] = '010'
    archivo.write_text(''.join(linea)+'\n')
    resultado = conciliar_depo(archivo)
    dato = resultado['campos_depo_extraidos'][0]
    assert dato['TASA_DE_INTERCAMBIO'] == '1470'
    assert dato['INDICADOR_CNB_CRUDO'] == '010'
    assert resultado['reglas_diagnosticas'][0]['decision_diagnostica'] == 'PERSISTIR_REGLA_VERIFICADA'
    assert resultado['agregados_depo']['resultados'] == []
    assert resultado['certificado_monetario'] is False


def test_control_no_se_certifica(tmp_path):
    archivo = tmp_path / 'depo.txt'
    archivo.write_text('05'+'0'*280+'\n')
    resultado = conciliar_depo(archivo)
    assert resultado['reglas_diagnosticas'][0]['decision_diagnostica'] == 'NO_PERSISTIR_CONTROL_RESUMEN'
    assert resultado['pendientes_clasificacion'] == []


def test_no_duplicar_fuentes(tmp_path):
    archivo = tmp_path / 'depo.txt'
    archivo.write_text('')
    with pytest.raises(ValueError, match='fuente_host'):
        conciliar_depo(archivo, movimientos_host=[{'fuente':'HA22'}])
