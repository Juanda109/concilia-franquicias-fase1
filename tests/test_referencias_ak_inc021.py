from openpyxl import Workbook
from app.services.fase2.referencias_ak_inc021 import auditar_ak


def test_conserva_referencia_valida_y_excluye_rota(tmp_path):
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'PLANTILLA (2)'
    hoja['C6'] = 'CONCEPTO A'
    hoja['AK9'] = '=CONCATENATE("17 ",C6)'
    hoja['AK6'] = '=CONCATENATE("17 ",#REF!)'
    ruta = tmp_path / 'muestra.xlsx'
    libro.save(ruta)
    resultado = auditar_ak(ruta)
    por_celda = {x['celda']: x for x in resultado['referencias']}
    assert por_celda['AK9']['estado'] == 'REFERENCIA_VALIDA'
    assert por_celda['AK9']['etiqueta'] == '17 CONCEPTO A'
    assert por_celda['AK6']['estado'] == 'REFERENCIA_ROTA_EXCLUIDA'
    assert por_celda['AK6']['etiqueta'] is None
    assert resultado['certificado'] is False


def test_origen_vacio_no_se_inventa(tmp_path):
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'PLANTILLA (2)'
    hoja['AK5'] = '=CONCATENATE("17 ",C99)'
    ruta = tmp_path / 'vacio.xlsx'
    libro.save(ruta)
    registro = auditar_ak(ruta)['referencias'][0]
    assert registro['estado'] == 'ORIGEN_C_NO_RESUELTO'
    assert registro['etiqueta'] is None
