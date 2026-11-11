from app.services.fase2.diagnostico_cnb_depo_inc57 import resumir_cnb
import pytest

def test_muestra_jornada_2590():
    valores = [117471, 65417, 34681, 2325]
    filas = [(2210, i, '02', '010', str(v).zfill(9)) for i, v in enumerate(valores, 1)]
    resultado = resumir_cnb(filas)
    assert resultado['concepto'] == '017-OP CNBS'
    assert resultado['cantidad'] == 4
    assert resultado['valor_total_crudo'] == '219894'
    assert resultado['cuenta'] is None
    assert resultado['valor_franquicia'] is None
    assert resultado['certificado_monetario'] is False

def test_excluye_no_cnb_y_control_resumen():
    resultado = resumir_cnb([(1,1,'06','999','999'),(1,2,'05','010','100'),(1,3,'02','011','20')])
    assert resultado['cantidad'] == 1
    assert resultado['valor_total_crudo'] == '20'

def test_rechaza_duplicados_y_no_numericos():
    with pytest.raises(ValueError):
        resumir_cnb([(1,1,'02','010','10'),(1,1,'02','010','10')])
    with pytest.raises(ValueError):
        resumir_cnb([(1,1,'02','010','10.00')])
