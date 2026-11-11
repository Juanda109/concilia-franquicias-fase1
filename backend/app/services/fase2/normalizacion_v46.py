"""Correccion no destructiva de salida V44: unidades, columnas reales y ausencias.
No sustituye formulas ni declara cruces certificados.
"""
from decimal import Decimal, InvalidOperation

def enriquecer(resultado):
    if not isinstance(resultado, dict):
        raise TypeError('resultado V44 invalido')
    calc=resultado.get('calculo') or {}
    filas=calc.get('resultados') or []
    nuevos=[]
    for original in filas:
        r=dict(original)
        valor=r.get('valor_base') if r.get('valor_base') is not None else r.get('valor')
        columna=r.get('columna_importe')
        if columna=='B':
            unidad='CANTIDAD_OPERACIONES'
            monetario=None
        elif columna in ('C','F'):
            unidad='IMPORTE_CANDIDATO_NO_HOMOLOGADO'
            monetario=valor
        else:
            unidad='FORMULA_COMPUESTA_PENDIENTE_HOMOLOGACION'
            monetario=None
        if valor is not None:
            try:
                n=Decimal(str(valor))
            except (InvalidOperation, ValueError, TypeError) as exc:
                raise ValueError('Resultado no numerico en '+str(r.get('celda'))) from exc
            if not n.is_finite():raise ValueError('Resultado no finito')
        r['valor_mostrable']=valor
        r['valor_monetario_candidato']=monetario
        r['unidad_v45']=unidad
        r['columna_libro_origen']={'B':'B','C':'C','F':'H'}.get(columna)
        r['certificado']=False
        nuevos.append(r)
    return {'id_jornada':resultado.get('id_jornada'),
            'registros':resultado.get('registros'),
            'filas_totales':resultado.get('filas_totales'),
            'resultados':nuevos,'certificado':False,
            'nota':'Comisiones en G/H del libro, E/F son nombres logicos V44. Cantidades B no son moneda. Sin homologacion Host.'}
