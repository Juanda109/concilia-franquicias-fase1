"""INC63: reconstruccion diagnostica desde PMD fuente y formulas del libro.
No escribe en el Excel, no consulta BD y no certifica resultados.
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from openpyxl import load_workbook
from validar_inc63_octubre import source_xls, embedded_pmd

INDICES = {'A': (3, 8), 'B': (4, 9), 'C': (5, 10)}
FORMULA = re.compile(r'^\s*=\+?IFERROR\(VLOOKUP\(\$?F\$?(\d+),PMD!\$C:\$N,(\d+),0\),0\)(\*-1)?\s*$', re.I)


def dec(x):
    if x is None: return None
    if isinstance(x, bool): raise ValueError('Importe booleano')
    try: result = Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError) as exc: raise ValueError(f'Importe invalido {x!r}') from exc
    if not result.is_finite(): raise ValueError('Importe no finito')
    return result


def nivel(x):
    return str(x).strip() if x is not None and str(x).strip() else None


def reconstruir(pmd, libro, permitir_periodos=False):
    fuente, controles = source_xls(Path(pmd))
    wbf = load_workbook(libro, read_only=True, data_only=False, keep_links=False)
    wbv = load_workbook(libro, read_only=True, data_only=True, keep_links=False)
    try:
        pmde, controles_libro = embedded_pmd(wbf['PMD'])
        diferencias_pmd = sum(a[0] != pmde[k][0] for k,a in fuente.items() if k in pmde)
        if set(fuente) != set(pmde) or diferencias_pmd:
            raise ValueError('PMD fuente no coincide con hoja PMD: no se puede reconstruir')
        ws = wbf['ESTRUCTURA']; valores = wbv['ESTRUCTURA']
        grupos = defaultdict(lambda: {'debito': Decimal(0), 'credito': Decimal(0), 'neto': Decimal(0), 'filas': []})
        estados = Counter(); excepciones = []; sin_nivel = []; integridad = []; comparacion = []
        vistos = set()
        for numero, (f, v) in enumerate(zip(
            ws.iter_rows(min_row=4,max_row=3245,min_col=5,max_col=16,values_only=True),
            valores.iter_rows(min_row=4,max_row=3245,min_col=5,max_col=16,values_only=True)
        ), start=4):
            if numero in vistos: raise ValueError('Fila duplicada')
            vistos.add(numero)
            tipo = nivel(f[0]); codigo = nivel(f[1]); niv = nivel(v[2]) or (codigo[:3] if codigo else None)
            if not niv:
                sin_nivel.append({'fila_excel':numero,'codigo':codigo,'debito':str(v[9]),'credito':str(v[10]),'neto':str(v[11])})
                continue
            if not tipo or tipo[:1] not in INDICES or not codigo:
                estados['SIN_REGLA_ECONOMICA'] += 1
                continue
            categoria = tipo[0]
            indices = []
            for pos in (9,10):
                literal = f[pos]
                match = FORMULA.fullmatch(str(literal or '').replace(' ',''))
                indices.append(int(match.group(2)) if match and int(match.group(1))==numero and (pos==9 or match.group(3)=='*-1') else None)
            if tuple(indices) != INDICES[categoria]:
                estados['FORMULA_EXCEPCIONAL_PENDIENTE'] += 1
                excepciones.append({'fila_excel':numero,'codigo':codigo,'categoria':categoria,'indices':indices})
                continue
            if codigo not in fuente:
                estados['SIN_CODIGO_PMD'] += 1
                continue
            medidas = fuente[codigo][0]
            di,ci=INDICES[categoria]
            debito = medidas[di-2]; credito = -medidas[ci-2]; neto = debito + credito
            grupo = grupos[niv]
            grupo['debito'] += debito; grupo['credito'] += credito; grupo['neto'] += neto; grupo['filas'].append(numero)
            estados['CALCULO_DIAGNOSTICO'] += 1
            almacenado = tuple(dec(v[pos]) for pos in (9,10,11))
            if all(x is not None for x in almacenado) and (debito,credito,neto) != almacenado:
                comparacion.append({'fila_excel':numero,'codigo':codigo,'nivel':niv,'reconstruido':[str(x) for x in (debito,credito,neto)],'almacenado':[str(x) for x in almacenado]})
            if neto != debito+credito: integridad.append(numero)
        val = wbv['VALIDADOR']; resultados=[]
        for numero in range(5,17):
            niv = nivel(val[f'C{numero}'].value)
            if not niv: continue
            g=grupos[niv]; pmd_nivel=fuente.get(niv)
            # H/I/J: indices 6,11,12 en PMD!C:N = posiciones 4,9,10 de las 11 medidas.
            h,i,j=(pmd_nivel[0][k] for k in (4,9,10)) if pmd_nivel else (None,None,None)
            f_actual=g['neto']; almacenado={k:dec(val[f'{c}{numero}'].value) for k,c in [('debito','D'),('credito','E'),('neto','F')]}
            resultados.append({'nivel':niv,'fila_validador':numero,'cantidad_filas':len(g['filas']),
                'debito_actual':str(g['debito']),'credito_actual':str(g['credito']),'F_neto_actual':str(f_actual),
                'H_pmd':None if h is None else str(h),'I_pmd':None if i is None else str(i),'J_pmd':None if j is None else str(j),
                'L_actual_F_mas_J':str(f_actual+j) if j is not None and permitir_periodos else None,
                'L_estado':'CALCULO_DIAGNOSTICO' if j is not None and permitir_periodos else 'PERIODO_NO_AUTORIZADO_O_PMD_AUSENTE',
                'validador_almacenado':{k:None if x is None else str(x) for k,x in almacenado.items()},
                'diferencia_neto_actual_vs_almacenado':None if almacenado['neto'] is None else str(f_actual-almacenado['neto']),
                'certificado':False})
        return {'estado':'DIAGNOSTICO_NO_CERTIFICADO','certificado':False,'fuente_pmd':Path(pmd).name,'libro':Path(libro).name,
            'sha256_libro':sha256(Path(libro).read_bytes()).hexdigest(), 'niveles_pmd':len(fuente),'diferencias_medidas_pmd':diferencias_pmd,
            'filas_rango_principal':3242,'proyecciones':dict(estados),'filas_sin_nivel':sin_nivel,
            'excepciones':excepciones,'filas_con_diferencia_vs_excel_almacenado':len(comparacion),'ejemplos_diferencias':comparacion[:20],
            'inconsistencias_calculo':integridad,'validador_principal':resultados,
            'cache_principal':'NO_DISPONIBLE_EN_ESTE_LIBRO; no se atribuye fecha ni historia a resultados almacenados',
            'bloque_secundario':'NO_INTEGRADO: origen ESTRUCTURA 2, control independiente',
            'nota':'Las fechas antiguas del libro no se usan como fecha de jornada; L requiere autorizacion expresa de compatibilidad de periodos.'}
    finally:
        wbf.close();wbv.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pmd',type=Path,required=True)
    parser.add_argument('--libro',type=Path,required=True)
    parser.add_argument('--salida',type=Path,required=True)
    parser.add_argument('--periodos-compatibles',action='store_true',help='Habilita L solo tras validar fechas funcionalmente')
    args=parser.parse_args()
    resultado=reconstruir(args.pmd,args.libro,args.periodos_compatibles)
    args.salida.write_text(json.dumps(resultado,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:resultado[k] for k in ('estado','niveles_pmd','filas_rango_principal','proyecciones','filas_con_diferencia_vs_excel_almacenado')},indent=2,ensure_ascii=False))

if __name__=='__main__': main()
