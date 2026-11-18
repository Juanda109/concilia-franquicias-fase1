from app.services.fase2.formulas_excel_redeban import indice_pmd,evaluar_fila

def test_importe_y_signo():
    idx=indice_pmd([{'NIVEL':'1.1','DEBITO_VALOR':'15','CREDITO_VALOR':'4','DEBITO_CANTIDAD':'2','CREDITO_CANTIDAD':'1'}])
    r=evaluar_fila(4,'1.1',{'N':'=+IFERROR(VLOOKUP($F4,PMD!$C:$N,3,0),0)','O':'=+IFERROR(VLOOKUP($F4,PMD!$C:$N,8,0),0)*-1','P':'=+N4+O4','Q':'=+IFERROR(VLOOKUP($F4,PMD!$C:$N,2,0),0)','R':'=+IFERROR(VLOOKUP($F4,PMD!$C:$N,7,0),0)'},idx)
    assert r['neto']['valor']=='11' and r['columnas']['Q']['valor']=='2'

def test_ausencia_no_es_cero():
    r=evaluar_fila(4,'NO_EXISTE',{'N':'=+IFERROR(VLOOKUP($F4,PMD!$C:$N,3,0),0)','O':'=+IFERROR(VLOOKUP($F4,PMD!$C:$N,8,0),0)*-1','P':'=+N4+O4'}, {})
    assert r['neto']['valor'] is None and r['columnas']['N']['excel_iferror']=='0'

def test_duplicado_no_asigna():
    idx=indice_pmd([{'NIVEL':'1.1','DEBITO_VALOR':'1'},{'NIVEL':'1.1','DEBITO_VALOR':'2'}])
    r=evaluar_fila(4,'1.1',{'N':'=+IFERROR(VLOOKUP($F4,PMD!$C:$N,3,0),0)','P':'=+N4+O4'},idx)
    assert r['columnas']['N']['estado']=='NIVEL_DUPLICADO'

def test_excepcional_bloqueada():
    r=evaluar_fila(4,'1.1',{'N':'=SUM(A1:A3)','P':'=+N4+O4'}, {})
    assert r['columnas']['N']['estado']=='FORMULA_NO_SOPORTADA'
