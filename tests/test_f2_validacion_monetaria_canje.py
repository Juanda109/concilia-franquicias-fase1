from decimal import Decimal
import pytest
from app.services.fase2.validacion_monetaria_canje import evaluar, decimal_o_nulo, ejecutar

def fila(**kw):
    return dict(tx='02',tipo='DEBITO',bin_dest='404279',vl_total='100',vl_interc='90',comision_op_exitosas=None,tii_recibida_emisor_visa_op_rever_ventas=None,**kw)

def test_comision_literal():
    x=evaluar(fila());assert x['comision_esperada']=='7450';assert x['estado_comision']=='NO_EVALUABLE_VALOR_ALMACENADO_NULO'

def test_bin_excluido():
    x=fila();x['bin_dest']='439467';assert evaluar(x)['comision_esperada']==''

def test_tii_credito_26():
    x=fila();x.update(tx='26',tipo='CREDITO',tii_recibida_emisor_visa_op_rever_ventas='10');assert evaluar(x)['estado_tii'].startswith('COINCIDE')

def test_tii_nulo():
    x=fila();x.update(tx='26',tipo='CREDITO');assert evaluar(x)['estado_tii']=='NO_EVALUABLE_VALOR_ALMACENADO_NULO'

def test_signo_efipago():
    x=fila();x.update(tx='22',tipo='EFIPAGO');assert evaluar(x)['control_signo']=='REQUIERE_IMPORTE_BRUTO'

def test_nulo_no_cero():
    assert decimal_o_nulo(None) is None and decimal_o_nulo('0')==Decimal(0)

def test_no_finitos():
    with pytest.raises(ValueError):decimal_o_nulo('NaN')

def test_base_restringida(tmp_path):
    with pytest.raises(ValueError):ejecutar([1,2],tmp_path/'salida','produccion')

def test_no_sobrescribir(tmp_path):
    with pytest.raises(FileExistsError):ejecutar([1,2],tmp_path,'concilia_test')
