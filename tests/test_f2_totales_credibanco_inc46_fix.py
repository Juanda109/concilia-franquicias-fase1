import pytest
from app.services.fase2.totales_credibanco_inc46_fix import construir_totales, proyectar_a_formulas

def fila(**kw):
    return {'cuenta':'CJE','tipo':'CREDITO','vl_interc':'10.25','vl_total':'11.00',
            'id_archivo':1,'linea_origen':1, **kw}

def test_conteo_no_es_importe():
    r=construir_totales([fila()])[0]
    assert (r['B'],r['C'],r['D'])==(1,'10.25','11.00')

def test_nulos_no_se_convierten_en_ceros():
    x=fila();x['vl_interc']=None;x['vl_total']=None
    r=construir_totales([x])[0];assert r['C'] is None and r['D'] is None

def test_cuenta_880_no_suma():
    x=fila();y=dict(x);y['familia']='cuenta_880'
    assert construir_totales([x,y])[0]['B']==1

def test_rechaza_duplicados():
    with pytest.raises(ValueError):construir_totales([fila(),fila()])

def test_suma_decimal():
    x=fila();y=fila();y['linea_origen']=2
    assert construir_totales([x,y])[0]['C']=='20.50'

def test_conteo_tipo_vacio():
    x=fila();x['tipo']=''
    assert construir_totales([x])[0]['B']==0

def test_formulas_b_c_diferentes():
    cat={'reglas':[{'fila':58,'cuenta':'123','concepto':'CJE','formula_G':'=VLOOKUP(C58,[2]TOTALES!$A:$B,2,0)','formula_F':None},
                   {'fila':60,'cuenta':'123','concepto':'CJE','formula_G':'=VLOOKUP(C60,[2]TOTALES!$A:$C,3,0)','formula_F':None}]}
    r=proyectar_a_formulas(construir_totales([fila()]),cat)
    assert r[0]['valor_proyectado']==1 and r[0]['unidad']=='CANTIDAD'
    assert r[1]['valor_proyectado']=='10.25' and r[1]['unidad']=='IMPORTE_ORIGEN'

def test_f90_pendiente():
    cat={'reglas':[{'fila':92,'cuenta':'123','concepto':'CJE','formula_F':'=VLOOKUP(C92,[2]TOTALES!$A:$B,2,0)-F90','formula_G':None}]}
    assert proyectar_a_formulas(construir_totales([fila()]),cat)[0]['estado']=='PENDIENTE_F90'
