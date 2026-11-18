"""INC57: evidencia cruda CNB segun clasificacion AU de la plantilla DEPO.
No interpreta moneda/escala ni asigna cuentas contables.
"""
from decimal import Decimal, InvalidOperation

CNB = frozenset({'010','011','012','110','111','112'})

def resumir_cnb(filas):
    """Filas: (id_archivo, linea_origen, tipo_movimiento, indicador_cash_back, valor_total)."""
    total = 0
    claves = set()
    lineas = []
    acumulado = Decimal(0)
    for archivo, linea, tipo, indicador, valor in filas:
        if str(indicador or '').strip() not in CNB or str(tipo or '').strip() == '05':
            continue
        clave = (int(archivo), int(linea))
        if clave in claves:
            raise ValueError('Linea DEPO CNB duplicada')
        claves.add(clave)
        texto = str(valor or '').strip()
        if not texto.isdigit():
            raise ValueError('Valor total crudo CNB no es entero no negativo')
        try:
            numero = Decimal(texto)
        except InvalidOperation as exc:
            raise ValueError('Valor crudo invalido') from exc
        acumulado += numero
        total += 1
        lineas.append({'id_archivo':clave[0], 'linea_origen':clave[1], 'valor_total_crudo':texto})
    return {'concepto':'017-OP CNBS', 'cantidad':total,
            'valor_total_crudo':str(acumulado), 'unidad':'UNIDADES_CRUDAS',
            'cuenta':None, 'valor_franquicia':None, 'total_host':None,
            'diferencia':None, 'certificado_monetario':False,
            'estado':'DIAGNOSTICO_NO_HOMOLOGADO', 'lineas_origen':lineas}
