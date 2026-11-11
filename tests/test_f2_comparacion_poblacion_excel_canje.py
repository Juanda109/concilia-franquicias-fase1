import csv
import json
from pathlib import Path
import pytest
from openpyxl import Workbook
from app.services.fase2.comparacion_poblacion_excel_canje import ejecutar, decimal_valor

CAMPOS = ['tipo_archivo','tx','tipo','cuenta','fecha_contable','vl_total','vl_interc','comision_op_exitosas','tii_recibida_emisor_visa_op_rever_ventas']

def preparar(tmp_path, fecha='2026-10-21'):
    plantilla = tmp_path/'plantilla.xlsx'
    wb = Workbook(); wb.active.title='plano'; wb.create_sheet('parte'); wb.create_sheet('BINES'); wb.save(plantilla)
    filas = ['CANT','08','CREDITO','017-ORIGINAL REEMBOLSOS CREDITO',fecha,'10','9','','']
    for nombre in ('canje.csv','excel.csv'):
        with (tmp_path/nombre).open('w',encoding='utf-8',newline='') as f:
            w=csv.writer(f);w.writerow(CAMPOS);w.writerow(filas)
    return tmp_path/'canje.csv', tmp_path/'excel.csv', plantilla

def test_sin_manifiesto_bloquea(tmp_path):
    a,b,c=preparar(tmp_path)
    r=ejecutar(a,b,c,tmp_path/'salida')
    assert not r['certificado'] and 'MANIFIESTO_POBLACION_AUSENTE' in r['bloqueos']

def test_fechas_distintas(tmp_path):
    a,b,c=preparar(tmp_path)
    contenido=b.read_text().replace('2026-10-21','2026-10-20'); b.write_text(contenido)
    r=ejecutar(a,b,c,tmp_path/'salida')
    assert 'FECHAS_NO_EQUIVALENTES' in r['bloqueos']

def test_no_sobrescribir(tmp_path):
    a,b,c=preparar(tmp_path)
    (tmp_path/'salida').mkdir()
    with pytest.raises(FileExistsError): ejecutar(a,b,c,tmp_path/'salida')

def test_nulo_distinto_cero():
    assert decimal_valor('') is None and decimal_valor('0') == 0

def test_no_finitos():
    with pytest.raises(ValueError): decimal_valor('NaN')

def test_grupo_y_sumas(tmp_path):
    a,b,c=preparar(tmp_path)
    r=ejecutar(a,b,c,tmp_path/'salida')
    assert len(r['grupos_diagnosticos'])==1
    assert r['grupos_diagnosticos'][0]['importes']['vl_total']['canje']=='10'

def test_huella_incorrecta_bloquea(tmp_path):
    a,b,c=preparar(tmp_path)
    m=tmp_path/'manifiesto.json'
    m.write_text(json.dumps({'fecha_contable':'2026-10-21','filtros':{},'escala_monetaria':'sin validar','poblacion_equivalente_aprobada':True,'responsable_aprobacion':'test','sha256_canje':'incorrecto','sha256_excel':'incorrecto','sha256_plantilla':'incorrecto'}))
    r=ejecutar(a,b,c,tmp_path/'salida',m)
    assert 'HUELLAS_MANIFIESTO_NO_COINCIDEN' in r['bloqueos'] and not r['certificado']
