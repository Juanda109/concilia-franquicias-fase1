"""Reproduccion verificable de TOTALES A3:D10 (pivot1) para Credibanco.
Referencia Excel solo documental; no requiere archivo XLSX en produccion.
No certifica equivalencia con jornada diferente ni ejecuta cruces Host.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

def numero(valor, campo):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{campo}: dato no numerico") from None
    if not d.is_finite():
        raise ValueError(f"{campo}: valor no finito")
    return d

def construir_totales(detalles):
    """Columnas A concepto, B COUNT(TIPO), C SUM(VL INTERC), D SUM(VL TOTAL).
    El conteo solo incluye TIPO no vacio. La suma ignora nulos, pero un
    grupo sin ningun importe conserva None (no un cero ficticio).
    No sumar familias cuenta_880: se trabaja sobre filas originales.
    """
    grupos = defaultdict(lambda: {'B': 0, 'C': Decimal(0), 'D': Decimal(0),
                                  'n_C': 0, 'n_D': 0, 'lineas': [], 'archivos': set()})
    vistos = set()
    for fila in detalles:
        if fila.get('familia') == 'cuenta_880':
            continue
        concepto = fila.get('cuenta')
        if not isinstance(concepto, str) or not concepto.strip():
            continue
        identidad = (fila.get('id_archivo'), fila.get('linea_origen'))
        if None not in identidad:
            if identidad in vistos:
                raise ValueError('Movimiento duplicado por archivo y linea')
            vistos.add(identidad)
        g = grupos[concepto]
        if fila.get('tipo') is not None and str(fila['tipo']).strip():
            g['B'] += 1
        for columna, origen in (('C', 'vl_interc'), ('D', 'vl_total')):
            d = numero(fila.get(origen), origen)
            if d is not None:
                g[columna] += d
                g['n_' + columna] += 1
        if identidad[1] is not None:
            g['lineas'].append(identidad[1])
        if identidad[0] is not None:
            g['archivos'].add(identidad[0])
    salida = []
    for concepto, g in sorted(grupos.items()):
        salida.append({'A': concepto, 'B': g['B'],
                       'C': str(g['C']) if g['n_C'] else None,
                       'D': str(g['D']) if g['n_D'] else None,
                       'archivos': sorted(g['archivos']),
                       'lineas_origen': g['lineas'],
                       'estado': 'PROYECCION_TABLA_DINAMICA_NO_HOMOLOGADA'})
    return salida

def proyectar_a_formulas(filas, catalogo):
    """No confundir B=conteo con importe. Solo vista diagnóstica."""
    indice = {f['A']: f for f in filas}
    resultado = []
    for regla in catalogo['reglas']:
        formula = regla.get('formula_F') or regla.get('formula_G') or ''
        columna = 'C' if '$A:$C,3,0' in formula else 'B'
        fila = indice.get(regla['concepto'])
        valor = fila.get(columna) if fila else None
        estado = ('PENDIENTE_ORIGEN' if fila is None else
                  'PENDIENTE_DATO' if valor is None else
                  'PENDIENTE_F90' if regla['fila'] == 92 else
                  'PROYECCION_NO_HOMOLOGADA')
        resultado.append({'celda': ('F' if regla.get('formula_F') else 'G') + str(regla['fila']),
                          'cuenta': regla['cuenta'], 'concepto': regla['concepto'],
                          'columna_totales': columna, 'valor_proyectado': valor,
                          'unidad': 'CANTIDAD' if columna == 'B' else 'IMPORTE_ORIGEN',
                          'estado': estado, 'certificado': False})
    return resultado
