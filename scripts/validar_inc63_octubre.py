"""INC63 Redeban: compara PMD fuente, hoja PMD del libro y formulas A/B/C.
Solo lectura. No certifica ni modifica archivos.
"""
import argparse
import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path
from openpyxl import load_workbook

CAMPOS = ('DEBITO_CANTIDAD','DEBITO_VALOR','DEBITO_COMISION_INTERCAMBIO','DEBITO_COMISION_ADMINISTRATIVA','DEBITO_NETO','CREDITO_CANTIDAD','CREDITO_VALOR','CREDITO_COMISION_INTERCAMBIO','CREDITO_COMISION_ADMINISTRATIVA','CREDITO_NETO','TOTAL')
INDICES = {'A':(3,8),'B':(4,9),'C':(5,10)}
LOOKUP = re.compile(r'VLOOKUP\s*\([^,;]+,\s*PMD!\$C:\$N,\s*(\d+)',re.I)

def d(x):
    if x is None or x == '':return Decimal(0)
    if isinstance(x,bool):raise ValueError('Booleano monetario')
    v=Decimal(str(x))
    if not v.is_finite():raise ValueError('Importe no finito')
    return v

def key(x):
    return str(x).strip() if x is not None and str(x).strip() else None

def source_xls(path):
    try:import xlrd
    except ImportError as exc:raise RuntimeError('Falta xlrd: ejecutar en el entorno .venv del proyecto, que ya lo utiliza') from exc
    book=xlrd.open_workbook(str(path)); sheet=book.sheet_by_name('PMD')
    rows={}; controls=[]
    for i in range(2,sheet.nrows):
        row=sheet.row_values(i); nivel=key(row[1]); nombre=key(row[0])
        if not nivel:continue
        values=tuple(d(row[j]) for j in range(2,13))
        if nivel=='999' and nombre and 'TOTAL PRODUCTOS PMD' in nombre.upper():
            controls.append((i+1,nivel,nombre));continue
        if nivel in rows:raise ValueError(f'Nivel operativo duplicado {nivel}')
        rows[nivel]=(values,nombre,i+1)
    return rows,controls

def embedded_pmd(ws):
    rows={}; controls=[]
    # PMD del libro tiene columna de nivel C, medidas D:N
    for i, values in enumerate(ws.iter_rows(min_row=4,max_col=14,values_only=True),4):
        nivel=key(values[2]); nombre=key(values[1]);
        if not nivel:continue
        vals=tuple(d(v) for v in values[3:14])
        if nivel=='999' and nombre and 'TOTAL PRODUCTOS PMD' in nombre.upper():
            controls.append((i,nivel,nombre));continue
        if nivel in rows:raise ValueError(f'Nivel PMD del libro duplicado {nivel}')
        rows[nivel]=(vals,nombre,i)
    return rows,controls

def analizar(xls,xlsx):
    fuente,controles=source_xls(xls)
    wb=load_workbook(xlsx,read_only=True,data_only=False,keep_links=False)
    try:
        pmde,ctrl_libro=embedded_pmd(wb['PMD'])
        comunes=set(fuente)&set(pmde)
        divergencias=[]
        for nivel in sorted(comunes):
            a=fuente[nivel][0];b=pmde[nivel][0]
            for idx,(x,y) in enumerate(zip(a,b)):
                if x!=y:
                    divergencias.append({'nivel':nivel,'medida':CAMPOS[idx],'fuente':str(x),'libro':str(y)})
        ws=wb['ESTRUCTURA']; formulas=Counter();proyectadas=Counter();excepciones=[];sin_pmd=Counter();ejemplos=[]
        for n, row in enumerate(ws.iter_rows(min_row=4,max_row=3245,min_col=5,max_col=16,values_only=True),4):
            tipo,codigo,nivel1,nivel2,*rest=row
            categoria=key(tipo)
            if not categoria or categoria[0] not in INDICES:continue
            categoria=categoria[0]; codigo=key(codigo)
            if not codigo:continue
            # N/O corresponden a indices 9 y 10 dentro de E:P (posiciones 9,10)
            db,cr=row[9],row[10]
            dbidx=LOOKUP.search(str(db or '')); cridx=LOOKUP.search(str(cr or ''))
            indices=(int(dbidx.group(1)) if dbidx else None,int(cridx.group(1)) if cridx else None)
            if indices!=INDICES[categoria]:
                excepciones.append({'fila':n,'codigo':codigo,'tipo':categoria,'indices':indices});continue
            formulas[categoria]+=1
            if codigo not in fuente:
                sin_pmd[categoria]+=1;continue
            # indices de VLOOKUP PMD!C:N: 3,4,5 -> E,F,G; 8,9,10 -> J,K,L
            valores=fuente[codigo][0]
            di,ci=INDICES[categoria]
            debito=valores[di-2];credito=valores[ci-2]
            neto=debito-credito
            proyectadas[categoria]+=1
            if len(ejemplos)<10:ejemplos.append({'fila':n,'codigo':codigo,'tipo':categoria,'neto_fuente':str(neto)})
        return {'estado':'DIAGNOSTICO_NO_CERTIFICADO','certificado':False,
                'fuente_pmd':xls.name,'libro':xlsx.name,
                'niveles_operativos_fuente':len(fuente),'niveles_operativos_hoja_pmd':len(pmde),
                'controles_fuente':controles,'controles_libro':ctrl_libro,
                'niveles_comunes':len(comunes),'niveles_solo_fuente':sorted(set(fuente)-set(pmde)),
                'niveles_solo_libro':sorted(set(pmde)-set(fuente)),
                'diferencias_medidas_pmd':len(divergencias),'ejemplos_diferencias_pmd':divergencias[:30],
                'formulas_estandar':dict(formulas),'proyecciones_con_pmd_fuente':dict(proyectadas),
                'formulas_sin_codigo_pmd_fuente':dict(sin_pmd),'formulas_excepcionales':excepciones,
                'ejemplos_proyecciones':ejemplos,
                'nota':'Las formulas se reconstruyen desde el PMD fuente; las fechas y los valores almacenados del libro no se asumen actuales.'}
    finally:wb.close()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pmd',type=Path,required=True);ap.add_argument('--libro',type=Path,required=True);ap.add_argument('--salida',type=Path,required=True);a=ap.parse_args()
    r=analizar(a.pmd,a.libro);a.salida.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in r.items() if k in ('estado','niveles_operativos_fuente','niveles_comunes','diferencias_medidas_pmd','formulas_estandar','proyecciones_con_pmd_fuente','formulas_sin_codigo_pmd_fuente')},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
