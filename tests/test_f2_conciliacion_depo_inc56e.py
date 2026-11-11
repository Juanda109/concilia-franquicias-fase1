import pytest
from app.services.fase2.conciliacion_depo_inc56e import sumar_contabilidad, estado_depo

def test_sumifs_cuentas_y_naturalezas():
    filas=[{'cuenta':'196095001838','naturaleza':'D','importe':'10.25'},
           {'cuenta':'196095001838','naturaleza':'D','importe':'2.75'},
           {'cuenta':'196095001838','naturaleza':'H','importe':'5'},
           {'cuenta':'196095001839','naturaleza':'D','importe':'7'},
           {'cuenta':'196095001839','naturaleza':'H','importe':'3'},
           {'cuenta':'OTRA','naturaleza':'D','importe':'999'}]
    x=sumar_contabilidad(filas)
    assert [(v['celda_excel'],v['importe_contable']) for v in x]==[('D2','13.00'),('D3','5'),('D4','7'),('D5','3')]

def test_no_infiere_importes_depo():
    assert estado_depo()['valor_franquicia'] is None
    assert estado_depo()['certificado_monetario'] is False

def test_rechaza_importes_invalidos():
    with pytest.raises(ValueError):
        sumar_contabilidad([{'cuenta':'196095001838','naturaleza':'D','importe':'NaN'}])

def test_vacio_no_equivale_a_certificacion():
    assert len(sumar_contabilidad([]))==4
    assert estado_depo()['diferencia'] is None
