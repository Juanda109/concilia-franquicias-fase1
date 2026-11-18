"""Evaluador conservador de N:R de ESTRUCTURA; no usa S/T/U."""
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

VLOOKUP = re.compile(r'^=\+?IFERROR\(VLOOKUP\(\$?F(?P<fila>\d+),PMD!\$?C:\$?N,(?P<indice>\d+),0\),0\)(?P<signo>\*-1)?$', re.I)
NETO = re.compile(r'^=\+?N(?P<fila>\d+)\+O(?P=fila)$', re.I)
# Indices relativos a C:N: D=2, E=3, F=4, G=5, I=7, J=8, K=9, L=10.
INDICES = {2:'DEBITO_CANTIDAD',3:'DEBITO_VALOR',4:'DEBITO_COMISION_INTERCAMBIO',5:'DEBITO_COMISION_ADMINISTRATIVA',7:'CREDITO_CANTIDAD',8:'CREDITO_VALOR',9:'CREDITO_COMISION_INTERCAMBIO',10:'CREDITO_COMISION_ADMINISTRATIVA'}


def indice_pmd(filas):
    d=defaultdict(list)
    for fila in filas:
        if not fila.get('ES_CONTROL'):
            d[str(fila['NIVEL']).strip()].append(fila)
    return d


def evaluar_busqueda(formula, numero, codigo, indice):
    m=VLOOKUP.fullmatch(str(formula or '').strip())
    if not m or int(m['fila']) != numero or int(m['indice']) not in INDICES:
        return {'estado':'FORMULA_NO_SOPORTADA','valor':None}
    encontrados=indice.get(str(codigo).strip(), [])
    if not encontrados:
        return {'estado':'SIN_COINCIDENCIA','valor':None,'excel_iferror': '0'}
    if len(encontrados)!=1:
        return {'estado':'NIVEL_DUPLICADO','valor':None,'cantidad':len(encontrados)}
    campo=INDICES[int(m['indice'])]
    valor=encontrados[0].get(campo)
    if valor is None or str(valor).strip()=='':
        return {'estado':'VALOR_AUSENTE','valor':None,'campo':campo}
    try:
        d=Decimal(str(valor))
    except InvalidOperation:
        return {'estado':'VALOR_INVALIDO','valor':None,'campo':campo}
    if not d.is_finite():
        return {'estado':'VALOR_INVALIDO','valor':None,'campo':campo}
    if m['signo']:
        d=-d
    return {'estado':'CALCULADO','valor':str(d),'campo':campo,
            'id_archivo':encontrados[0].get('id_archivo'),
            'linea_pmd':encontrados[0].get('numero_linea')}


def evaluar_fila(numero,codigo,formulas,indice):
    resultado={'fila_excel':numero,'codigo_operacion':codigo,'columnas':{},'certificado':False}
    for col in ('N','O','Q','R'):
        resultado['columnas'][col]=evaluar_busqueda(formulas.get(col),numero,codigo,indice)
    p=formulas.get('P')
    if not NETO.fullmatch(str(p or '').strip()) or int(NETO.fullmatch(str(p or '').strip())['fila'])!=numero:
        resultado['neto']={'estado':'FORMULA_NO_SOPORTADA','valor':None}
    elif all(resultado['columnas'][col]['estado']=='CALCULADO' for col in ('N','O')):
        resultado['neto']={'estado':'CALCULADO','valor':str(Decimal(resultado['columnas']['N']['valor'])+Decimal(resultado['columnas']['O']['valor']))}
    else:
        resultado['neto']={'estado':'OPERANDOS_NO_RESUELTOS','valor':None}
    return resultado
