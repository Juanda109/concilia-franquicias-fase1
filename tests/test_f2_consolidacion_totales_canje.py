import csv
import json
from decimal import Decimal
import pytest
from app.services.fase2.consolidacion_totales_canje import consolidar, decimal_excel, ejecutar


def fila(**kwargs):
    base = {'TX': '02', 'TIPO': 'CREDITO', 'cuenta': 'CTA', 'cuentas comisiones': 'COM', 'cuenta 880': '',
            'VL TOTAL': '100', 'VL INTERC': '90', 'COMISION OP EXITOSAS': '5',
            'TII RECIBIDA EMISOR VISA OP REVER VENTAS': ''}
    base.update(kwargs)
    return base


def test_cuenta_principal():
    r = consolidar([fila(), fila(**{'VL TOTAL': '20', 'VL INTERC': '10'})])
    assert r['principal']['CTA'] == {'cantidad_tipo': 2, 'vl_interc': Decimal(100), 'vl_total': Decimal(120)}


def test_cuenta_tipo_no_vacio():
    r = consolidar([fila(TIPO='')])
    assert r['principal']['CTA']['cantidad_tipo'] == 0


def test_comisiones_y_tii():
    r = consolidar([fila(**{'cuentas comisiones': '017-CJE REC VISA NAL VR COM EXIT TC BATC',
                              'TII RECIBIDA EMISOR VISA OP REVER VENTAS': '3'})])
    assert r['L3_comisiones_exitosas'] == Decimal(5)
    assert r['comisiones']['017-CJE REC VISA NAL VR COM EXIT TC BATC']['tii'] == Decimal(3)


def test_regalo_independiente():
    r = consolidar([fila(**{'cuenta 880': 'REGALO'})])
    assert r['cuenta_880']['REGALO']['vl_total'] == Decimal(100)
    assert r['principal']['CTA']['vl_total'] == Decimal(100)


def test_totales_y_vacios_excluidos():
    r = consolidar([fila(TX='Totales'), fila(TX=''), fila()])
    assert r['conteos'] == {'entrada': 3, 'detalle': 1, 'totales': 1, 'sin_tx': 1}


def test_nulo_no_equivale_a_cero():
    r = consolidar([fila(**{'VL INTERC': ''}), fila(**{'VL INTERC': '0'})])
    assert r['nulos']['VL INTERC'] == 1
    assert r['principal']['CTA']['vl_interc'] == 0


def test_no_finitos():
    with pytest.raises(ValueError):
        decimal_excel('NaN')


def test_no_numerico():
    with pytest.raises(ValueError):
        consolidar([fila(**{'VL TOTAL': 'no_es_numero'})])


def test_l5_l8_sin_inventar():
    r = consolidar([fila()])
    assert r['L5_carta'] is None and r['L8_cuota_red'] is None and not r['certificado']


def test_entrada_csv_y_salida(tmp_path):
    entrada = tmp_path / 'entrada.csv'
    datos = fila()
    with entrada.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(datos), delimiter=';')
        writer.writeheader()
        writer.writerow(datos)
    salida = tmp_path / 'salida'
    resultado = ejecutar(entrada, salida)
    assert resultado['conteos']['detalle'] == 1
    assert (salida / 'informe.json').exists()
    assert (salida / 'principal.csv').exists()
    assert (salida / 'comisiones.csv').exists()
    assert (salida / 'cuenta_880.csv').exists()
    assert json.loads((salida / 'informe.json').read_text(encoding='utf-8'))['certificado'] is False
    with pytest.raises(FileExistsError):
        ejecutar(entrada, salida)


def test_columnas_requeridas(tmp_path):
    entrada = tmp_path / 'in.csv'
    entrada.write_text('TX;TIPO\n02;DEBITO\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Columnas faltantes'):
        ejecutar(entrada, tmp_path / 'out')
