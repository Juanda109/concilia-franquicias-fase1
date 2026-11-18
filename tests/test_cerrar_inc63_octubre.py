import sys
from pathlib import Path
from decimal import Decimal
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from cerrar_inc63_octubre import dec, FORMULA, reconstruir


def test_decimal():
    assert dec('0.01') == Decimal('0.01')
    assert dec(None) is None
    with pytest.raises(ValueError): dec('NaN')


def test_formula_estricta():
    assert FORMULA.fullmatch('=+IFERROR(VLOOKUP($F8,PMD!$C:$N,3,0),0)')
    assert not FORMULA.fullmatch('=IFERROR(VLOOKUP($F8,PMD!$C:$N,3,0),0)+100')


def test_formula_credito():
    assert FORMULA.fullmatch('=+IFERROR(VLOOKUP($F8,PMD!$C:$N,8,0),0)*-1')


def test_integracion_libro(monkeypatch):
    # La muestra PMD ya contrastada se toma de la hoja PMD del libro para esta prueba sin xlrd.
    from openpyxl import load_workbook
    from validar_inc63_octubre import embedded_pmd
    ruta=Path('/mnt/data/Estructura Cuadre Redeban 20261002.xlsx')
    if not ruta.exists(): pytest.skip('Plantilla no disponible')
    wb=load_workbook(ruta,read_only=True,data_only=False)
    try: filas, controles=embedded_pmd(wb['PMD'])
    finally: wb.close()
    monkeypatch.setattr('cerrar_inc63_octubre.source_xls',lambda p:(filas,controles))
    r=reconstruir('PMDGeneralEntidad20261002.xls',ruta)
    assert r['niveles_pmd']==331
    assert r['proyecciones']['CALCULO_DIAGNOSTICO']==618
    assert r['proyecciones']['FORMULA_EXCEPCIONAL_PENDIENTE']==4
    assert r['proyecciones']['SIN_CODIGO_PMD']==2616
    assert r['certificado'] is False
    assert all(x['L_actual_F_mas_J'] is None for x in r['validador_principal'])
