"""Clasificacion diagnostica DEPO; reglas de plantilla AU, no asiento contable."""
from decimal import Decimal

CNB = frozenset({'010','011','012','110','111','112'})

def clasificar(tipo, oficina, indicador, amex):
    tipo = str(tipo or '').strip()
    oficina = str(oficina or '').strip()
    indicador = str(indicador or '').strip()
    amex = str(amex or '').strip().upper()
    if tipo == '05':
        return 'CONTROL_RESUMEN_EXCLUIDO'
    if indicador in CNB:
        return '017-OP CNBS'
    if tipo == '06':
        if oficina != '0090' and amex in ('', 'AMEX NACIONAL'):
            return '017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS'
        if (oficina == '0090' and amex != 'AMEX INTERNACIONAL') or (oficina != '0090' and amex == 'AMEX INTERNACIONAL'):
            return '017-VR. DEPOSITOS ELECTRONICOS INTERNACIONAL CONSIGNADOS'
    if tipo == '26':
        if oficina != '0090' and amex in ('', 'AMEX NACIONAL'):
            return '017-VR. REVERSIONES D.E. NACIONAL'
        if oficina in ('0090','0075') and amex in ('', 'AMEX INTERNACIONAL'):
            return '017-VR. REVERSIONES D.E. INTERNACIONAL'
    if tipo == '02' and oficina != '0090':
        return '017-VR. RET ATMs ADQUIRIENTES EN BBV NAL'
    return 'SIN_CLASIFICACION_AU'

def agrupar(filas):
    """Filas: archivo,linea,tipo,oficina,indicador,amex,valor_total.
    Ningun importe crudo se interpreta como COP.
    """
    grupos = {}
    claves = set()
    for archivo, linea, tipo, oficina, indicador, amex, valor in filas:
        clave = (int(archivo), int(linea))
        if clave in claves:
            raise ValueError('Linea DEPO duplicada')
        claves.add(clave)
        concepto = clasificar(tipo, oficina, indicador, amex)
        if concepto == 'CONTROL_RESUMEN_EXCLUIDO':
            continue
        g = grupos.setdefault(concepto, {'concepto': concepto, 'cantidad': 0,
            'suma': Decimal('0'), 'invalidos': 0, 'lineas_origen': []})
        g['cantidad'] += 1
        texto = str(valor or '').strip()
        if texto.isdigit():
            g['suma'] += Decimal(texto)
        else:
            g['invalidos'] += 1
        g['lineas_origen'].append({'id_archivo': clave[0], 'linea_origen': clave[1]})
    resultado = []
    for concepto in sorted(grupos):
        g = grupos[concepto]
        resultado.append({'concepto': concepto, 'cantidad': g['cantidad'],
            'valor_total_crudo': str(g['suma']) if not g['invalidos'] else None,
            'registros_sin_valor': g['invalidos'], 'unidad': 'UNIDADES_CRUDAS',
            'cuenta': None, 'valor_franquicia': None, 'total_host': None,
            'diferencia': None, 'certificado_monetario': False,
            'estado': 'DIAGNOSTICO_NO_HOMOLOGADO', 'lineas_origen': g['lineas_origen']})
    return resultado
