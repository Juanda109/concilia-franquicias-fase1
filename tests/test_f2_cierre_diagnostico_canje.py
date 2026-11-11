import csv
import json
from pathlib import Path
import pytest
from app.services.fase2.cierre_diagnostico_canje import analizar, ejecutar, ESTADO


def fixture(tmp_path, interc='658'):
    base = tmp_path / 'base'
    for p in ('parser', 'consolidacion', 'validacion'):
        (base / p).mkdir(parents=True)
    (base / 'parser' / 'informe.json').write_text(json.dumps({'registros_plano': 2, 'sha256_plantilla': 'abc', 'certificado': False}))
    (base / 'consolidacion' / 'informe.json').write_text(json.dumps({'conteos': {'entrada': 2, 'detalle': 1, 'totales': 1, 'sin_tx': 0}}))
    (base / 'validacion' / 'informe.json').write_text(json.dumps({'registros_plano': 2, 'sha256_plantilla': 'abc', 'diferencias_total': 1, 'L3_python': '22350', 'L3_cache_excel': '106952200'}))
    (base / 'validacion' / 'diferencias.json').write_text(json.dumps({'principal': [], 'comisiones': [], 'cuenta_880': [{'cuenta': '', 'campo': 'vl_interc', 'estado': 'DIFERENCIA', 'python': '6179055', 'excel_cache': '6179712'}]}))
    with (base / 'parser' / 'parte_python.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['TX', 'VL INTERC', 'cuenta'], delimiter=';')
        w.writeheader()
        w.writerow({'TX': 'Totales', 'VL INTERC': interc, 'cuenta': ''})
        w.writerow({'TX': '02', 'VL INTERC': '10', 'cuenta': 'cuenta'})
    return base

def test_estado(tmp_path):
    assert analizar(fixture(tmp_path))[0]['estado'] == ESTADO

def test_no_certificado(tmp_path):
    assert analizar(fixture(tmp_path))[0]['certificado'] is False

def test_conteos(tmp_path):
    assert analizar(fixture(tmp_path))[0]['conteos']['detalle'] == 1

def test_control_separado(tmp_path):
    assert analizar(fixture(tmp_path))[0]['intercambio_registros_control_literal'] == '658'

def test_delta_657(tmp_path):
    assert analizar(fixture(tmp_path))[0]['diferencia_intercambio_cache_menos_python_cuenta_880'] == '657'

def test_diferencia_unica(tmp_path):
    assert analizar(fixture(tmp_path))[0]['diferencias_total'] == 1

def test_l8_no_calculada(tmp_path):
    assert analizar(fixture(tmp_path))[0]['L8'] == 'NO_CALCULADA'

def test_siete_host(tmp_path):
    assert analizar(fixture(tmp_path))[0]['correspondencias_host_pendientes_homologacion'] == 7

def test_archivos_salida(tmp_path):
    base = fixture(tmp_path)
    ejecutar(base, tmp_path / 'out')
    assert (tmp_path / 'out' / 'informe_cierre.json').is_file()
    assert (tmp_path / 'out' / 'diferencias_cierre.csv').is_file()

def test_no_sobrescribir(tmp_path):
    base = fixture(tmp_path)
    ejecutar(base, tmp_path / 'out')
    with pytest.raises(FileExistsError):
        ejecutar(base, tmp_path / 'out')

def test_hash_distinto(tmp_path):
    base = fixture(tmp_path)
    (base / 'parser' / 'informe.json').write_text(json.dumps({'registros_plano': 2, 'sha256_plantilla': 'diferente'}))
    assert any('Hash' in x for x in analizar(base)[0]['inconsistencias_de_integridad'])

def test_csv_faltante(tmp_path):
    base = fixture(tmp_path)
    (base / 'parser' / 'parte_python.csv').unlink()
    with pytest.raises(FileNotFoundError):
        analizar(base)
