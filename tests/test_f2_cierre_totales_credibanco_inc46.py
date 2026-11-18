from app.services.fase2.cierre_totales_credibanco_inc46 import cerrar

def test_cierre_no_certifica_ni_suma_cantidades_como_dinero():
    filas=[dict(id_archivo=1,linea_origen=1,tipo_archivo='CANT',cuenta='CONCEPTO',tipo='CREDITO',vl_interc='15.50',vl_total='16')]
    catalogo={'reglas':[dict(fila=58,cuenta='299095302',concepto='CONCEPTO',formula_G='=VLOOKUP(C58,[2]TOTALES!$A:$B,2,0)',formula_F=None),dict(fila=60,cuenta='299095302',concepto='CONCEPTO',formula_G='=VLOOKUP(C60,[2]TOTALES!$A:$C,3,0)',formula_F=None)]}
    out=cerrar(filas,catalogo,1377)
    assert out['certificado'] is False
    assert out['formulas'][0]['valor_formula_final']==1
    assert out['formulas'][0]['valor_franquicia'] is None
    assert out['formulas'][1]['valor_formula_final']=='15.50'

def test_f90_no_se_infiere_de_la_muestra():
    filas=[dict(id_archivo=1,linea_origen=1,tipo_archivo='CANT',cuenta='CONCEPTO',tipo='CREDITO',vl_interc='15.50',vl_total='16')]
    catalogo={'reglas':[dict(fila=92,cuenta='299095843',concepto='CONCEPTO',formula_F='=VLOOKUP(C92,[2]TOTALES!$A:$B,2,0)-F90',formula_G=None)]}
    out=cerrar(filas,catalogo,1377)
    assert out['formulas'][0]['estado']=='PENDIENTE_VALIDACION_F90'
    assert out['formulas'][0]['valor_formula_final'] is None
