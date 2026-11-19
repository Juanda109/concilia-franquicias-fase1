from decimal import Decimal
import pytest
from app.services.fase2.paridad_plantilla_inc021 import evaluar, diagnostico_paridad, DependenciaNoResuelta


def test_subtotales_y_diferencia():
    formulas = {'F42':'=SUM(F6:F7)','F6':Decimal('10.20'),'F7':Decimal('1.30'),
                'G42':'=SUM(G6:G7)','G6':Decimal('9.00'),'G7':Decimal('1.00'),
                'F210':'=+F42+F5','G210':'=+G42+G5','G211':'=+F210-G210'}
    valores = {'F5':'2.00','G5':'0.00'}
    assert evaluar('F42',valores,formulas) == Decimal('11.50')
    assert evaluar('G211',valores,formulas) == Decimal('3.50')


def test_no_inventa_valor_para_busqueda_externa():
    with pytest.raises(DependenciaNoResuelta):
        evaluar('F42',{}, {'F42':'=SUM(F6:F6)','F6':'=VLOOKUP(C6,[2]TOTALES!A:B,2,0)'})


def test_rechaza_circularidad():
    with pytest.raises(DependenciaNoResuelta):
        evaluar('F6',{}, {'F6':'=+F7','F7':'=+F6'})


def test_rechaza_importe_no_finito():
    with pytest.raises(DependenciaNoResuelta):
        evaluar('F6',{'F6':'NaN'}, {})


def test_resultado_no_certifica(tmp_path):
    from openpyxl import Workbook
    libro=Workbook(); hoja=libro.active; hoja.title='PLANTILLA (2)'
    hoja['F42']='=SUM(F6:F7)'; hoja['F6']=10; hoja['F7']=20
    ruta=tmp_path/'prueba.xlsx'; libro.save(ruta)
    resultado=diagnostico_paridad(ruta,{})
    assert resultado['celdas']['F42']['valor']=='30'
    assert resultado['celdas']['G211']['estado']=='DEPENDENCIA_PENDIENTE'
    assert resultado['certificado'] is False
    assert resultado['conciliado_host'] is False
    assert resultado['homologado_contablemente'] is False


def test_referencia_interna_otra_columna():
    assert evaluar('F5', {}, {'F5':'=+N170','N170':Decimal('123.45')}) == Decimal('123.45')


def test_operaciones_y_parentesis():
    formulas={'F6':'=(M18+N18)*2-G6','M18':Decimal('10'),'N18':Decimal('5'),'G6':Decimal('3')}
    assert evaluar('F6',{},formulas)==Decimal('27')


def test_no_acepta_referencia_externa_ni_rota():
    for formula in ('=VLOOKUP(C6,[2]TOTALES!A:B,2,0)', '=+N170+#REF!'):
        with pytest.raises(DependenciaNoResuelta):
            evaluar('F6',{}, {'F6':formula})


def test_sum_no_oculta_error_en_dependencia():
    with pytest.raises(DependenciaNoResuelta):
        evaluar('F42',{}, {'F42':'=SUM(F6:F7)','F6':'=+N170+#REF!','F7':4})


def test_suma_referencias_reales_plantilla():
    formulas={'F99':'=+F98+F56+F42','F98':Decimal('5'),'F56':Decimal('3'),'F42':Decimal('2'),
              'F210':'=+F208+F122+F99+F4+F5','F208':Decimal('10'), 'F122':Decimal('20'),
              'F4':Decimal('1'),'F5':Decimal('4'), 'G210':'=+G208+G122+G99+G4+G5',
              'G208':Decimal('1'),'G122':Decimal('2'),'G99':Decimal('3'),'G4':Decimal('4'),
              'G211':'=+F210-G210'}
    assert evaluar('F99',{},formulas)==Decimal('10')
    assert evaluar('G211',{},formulas)==Decimal('35')
