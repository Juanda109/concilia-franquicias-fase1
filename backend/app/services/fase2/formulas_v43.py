"""Evaluacion literal de formulas TOTALES de Credibanco.

No presupone que una columna TOTALES equivalga a un campo crudo CAET/CANT.
La entrada se recibe tras reproducir y validar la construccion de TOTALES.
"""
from decimal import Decimal, InvalidOperation

# fila, cuenta, concepto, clave de busqueda, columna resultado, celda
REGLAS = (
 (57,'299095302','017-CANJE RECIBIDO TARJETA CREDITO','A','B','F57'),
 (58,'299095302','017-CANJE RECIBIDO TARJETA CREDITO PAGOS','A','B','G58'),
 (59,'299095302','017-CANJE RECIBIDO TARJETA CREDITO REVERSION VENTAS 26 VLR. TOTAL','A','C','G59'),
 (60,'299095302','017-ORIGINAL REEMBOLSOS CREDITO','A','C','G60'),
 (61,'299095302','017-CANJE RECIBIDO TC REVERSION AVANCES 22','A','B','G61'),
 (62,'299095302','017-CANJE RECIBIDO TC REVERSION PAGOS 24','A','B','F62'),
 (66,'299095301','017-CANJE RECIBIDO TARJETA DEBITO','A','B','F66'),
 (67,'299095301','017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES','A','B','G67'),
 (68,'299095301','017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES PAGOS','A','B','F68'),
 (69,'299095301','017-ORIGINAL REEMBOLSOS DEBITO','A','C','G69'),
 (75,'299095300','017-COMISIONES EXIT. TARJETA DEBITO ONLINE','E','F','F75'),
 (84,'299095880','017-CANJE RECIBIDO TARJETA DEBITO REGALO','A','C','F84'),
 (85,'299095880','017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES REGALO','A','C','G85'),
)

def _decimal(valor):
    if valor is None or isinstance(valor,(bool,float)):
        raise ValueError('Importe ausente o tipo no exacto')
    try:
        d=Decimal(str(valor))
    except (InvalidOperation,TypeError,ValueError) as exc:
        raise ValueError('Importe invalido') from exc
    if not d.is_finite():raise ValueError('Importe no finito')
    return d

def evaluar(filas_totales, referencias=None):
    """Devuelve formulas calculadas y pendientes; nunca certifica conciliacion.

    referencias: valores explicitamente sustentados para celdas I55,G78,G65.
    F57 = (B57 + I55) + G78 + G65; la ausencia no se transforma en cero.
    """
    referencias=referencias or {}
    indices={'A':{},'E':{}}
    for fila in filas_totales:
        for clave in indices:
            texto=str(fila.get(clave) or '').strip()
            if texto:
                if texto in indices[clave]:raise ValueError('Clave duplicada: '+texto)
                indices[clave][texto]=fila
    calculadas={}
    resultado=[]
    for numero,cuenta,concepto,busqueda,columna,celda in REGLAS:
        origen=indices[busqueda].get(concepto)
        valor=None
        estado='SIN_CONCEPTO_TOTALES' if origen is None else 'SIN_IMPORTE_TOTALES'
        if origen is not None and origen.get(columna) is not None:
            valor=_decimal(origen[columna])
            estado='BASE_TOTALES_CALCULADA_NO_HOMOLOGADA'
            calculadas[celda]=valor
        resultado.append({'cuenta':cuenta,'concepto':concepto,'celda':celda,
                          'columna_busqueda':busqueda,'columna_importe':columna,
                          'valor_base':str(valor) if valor is not None else None,
                          'estado':estado,'certificado':False})
    def compuesto(celda,cuenta,terminos):
        faltantes=[ref for _,ref in terminos if ref not in calculadas and ref not in referencias]
        if faltantes:
            return {'cuenta':cuenta,'celda':celda,'valor':None,
                    'estado':'DEPENDENCIAS_PENDIENTES','faltantes':faltantes,'certificado':False}
        total=sum((signo*(calculadas[ref] if ref in calculadas else _decimal(referencias[ref]))
                   for signo,ref in terminos),Decimal('0'))
        calculadas[celda]=total
        return {'cuenta':cuenta,'celda':celda,'valor':str(total),
                'estado':'FORMULA_COMPUESTA_NO_HOMOLOGADA','certificado':False}
    resultado.append(compuesto('F57_COMPLETA','299095302',[(1,'F57'),(1,'I55'),(1,'G78'),(1,'G65')]))
    resultado.append(compuesto('I57','299095302',[(1,'F57_COMPLETA'),(-1,'G58'),(-1,'G59'),(-1,'G61'),(-1,'G60'),(1,'F62')]))
    return {'resultados':resultado,'certificado':False,'celdas_calculadas':len(calculadas),
            'advertencia':'TOTALES debe derivarse de las estructuras originales y validar unidad, signo y fecha antes de homologar Host.'}
