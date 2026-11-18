from decimal import Decimal
from pathlib import Path
import pytest
from openpyxl import Workbook
from app.services.fase2.parser_parte_canje import (
    mid, numero, tipo_tarjeta, modalidad, cuenta_principal,
    parsear_registro, ejecutar, HEADERS
)


def registro(tx='02', bin_dest='404279', bin_tarjeta='404279', total='000001230', interc='000000230', modo='00', error='00', motivo='00'):
    s = [' '] * 280
    def poner(pos, valor):
        s[pos-1:pos-1+len(valor)] = list(valor)
    poner(1,tx); poner(9,bin_dest); poner(15,'030726')
    poner(56,'000'+bin_tarjeta+'0000000000')
    poner(123,total); poner(141,interc); poner(152,motivo)
    poner(198,error); poner(266,modo)
    return ''.join(s)


def test_posiciones():
    r = registro()
    assert mid(r,123,9) == '000001230'
    assert mid(r,141,9) == '000000230'
    assert len(HEADERS) == 22


def test_bin_tarjeta_independiente():
    r = registro(bin_dest='462550', bin_tarjeta='404279')
    v = parsear_registro(r, {'404279':'DEBITO'})
    assert v['BIN DEST'] == 462550
    assert v['TIPO'] == 'DEBITO'
    assert v['cuenta 880'].endswith('REGALO')


def test_error_no_cuenta_principal():
    v = parsear_registro(registro(error='05'), {'404279':'DEBITO'})
    assert v['cuenta'] == ''


def test_cnb_y_manual():
    assert modalidad(registro(modo='10'), '02') == 'CNB'
    assert modalidad(registro(modo='  '), '02') == 'Manual'
    assert modalidad(registro(modo='00'), '02') == 'ELECTRONICO'


def test_totales_impar():
    v = parsear_registro(registro(tx='05'), {'404279':'DEBITO'})
    assert v['TX'] == 'Totales'
    assert v['ESPACIOS'] == 'Totales'


def test_comision_y_exclusion():
    cat = {'404279':'DEBITO'}
    assert parsear_registro(registro(), cat)['COMISION OP EXITOSAS'] == Decimal('7450')
    assert parsear_registro(registro(bin_dest='439467'), cat)['COMISION OP EXITOSAS'] is None


def test_efipago_signo():
    v = parsear_registro(registro(tx='22',bin_tarjeta='439467'), {'439467':'EFIPAGO'})
    assert v['VL INTERC'] == Decimal('-230')
    assert v['cuenta'] == '017-VISA PAGOS'


def test_tii():
    v = parsear_registro(registro(tx='26'), {'404279':'CREDITO'})
    assert v['TII RECIBIDA EMISOR VISA OP REVER VENTAS'] == Decimal('1000')
    assert v['cuentas comisiones'].startswith('017-TII')


def test_tx42_precedencia():
    assert cuenta_principal('42',404279,'CREDITO','05','00','ELECTRONICO') == '017-COMISIONES NO EXITOSAS TD Y TC IMPUTABLES BANCO'
    assert cuenta_principal('42',404279,'CREDITO','15','00','ELECTRONICO') == '017-COMISIONES NO EXITOSAS TD Y TC  TIPO 15 Y 16'
    assert cuenta_principal('42',404279,'CREDITO','03','00','ELECTRONICO') == '017-NOTAS DEBITO CANJE RECIBIDO'


def test_nulos_no_cero():
    assert numero('         ') is None
    assert numero('notnumber') is None
    assert numero('000000000') == 0


def test_catalogo_faltante():
    assert tipo_tarjeta('0009999990000000000', {}) == ''


def test_ejecutar_no_sobrescribe(tmp_path):
    w = Workbook()
    ws = w.active; ws.title = 'plano'; ws['A1'] = registro()
    b = w.create_sheet('BINES'); b['D4'] = 404279; b['E4'] = 'DEBITO'
    ruta = tmp_path / 'entrada.xlsx'; w.save(ruta)
    salida = tmp_path / 'salida'
    informe = ejecutar(ruta, salida)
    assert informe['registros_plano'] == 1
    assert informe['certificado'] is False
    assert (salida / 'parte_python.csv').exists()
    with pytest.raises(FileExistsError):
        ejecutar(ruta, salida)
