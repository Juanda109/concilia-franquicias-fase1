from app.services.fase2.clasificacion_depo_integral import clasificar, agrupar

def test_cnb_jornadas():
    for archivo, valores, esperado in ((3486,[117472,65418,34682,2326],'219898'),
                                       (2210,[117471,65417,34681,2325],'219894')):
        filas = [(archivo,i,'02','0010','010',None,str(v).zfill(9)) for i,v in enumerate(valores,1)]
        resultado = agrupar(filas)
        assert len(resultado) == 1
        assert resultado[0]['concepto'] == '017-OP CNBS'
        assert resultado[0]['valor_total_crudo'] == esperado
        assert resultado[0]['cantidad'] == 4
        assert resultado[0]['valor_franquicia'] is None

def test_depositos_y_reversiones():
    assert 'NAL CONSIGNADOS' in clasificar('06','0001',None,'')
    assert 'INTERNACIONAL CONSIGNADOS' in clasificar('06','0090',None,'')
    assert 'REVERSIONES D.E. NACIONAL' in clasificar('26','0001',None,'')
    assert 'REVERSIONES D.E. INTERNACIONAL' in clasificar('26','0090',None,'')

def test_controles_y_sin_clasificacion():
    assert agrupar([(1,1,'05','0001','010',None,'123')]) == []
    assert agrupar([(1,1,'06','0001',None,None,'abc')])[0]['valor_total_crudo'] is None
    assert agrupar([(1,1,'06','0001',None,None,'abc')])[0]['registros_sin_valor'] == 1
    assert clasificar('99','0001',None,None) == 'SIN_CLASIFICACION_AU'

def test_duplicados():
    import pytest
    with pytest.raises(ValueError):
        agrupar([(1,1,'02','0001','010',None,'10')]*2)
