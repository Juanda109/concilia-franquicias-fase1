"""INC56-G: agregador monetario controlado DEPO; no certifica escala ni reglas Excel.

Recibe movimientos previamente parseados, clasificados y validados por un proceso
externo. Nunca infiere cuentas, signos, escala, CNB o AMEX desde campos crudos.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

CONCEPTOS = frozenset({
    'DEPOSITO_NACIONAL', 'DEPOSITO_INTERNACIONAL',
    'REVERSION_NACIONAL', 'REVERSION_INTERNACIONAL',
})


def _decimal(valor, etiqueta):
    if isinstance(valor, float) or isinstance(valor, bool):
        raise ValueError(f'{etiqueta}: usar Decimal o texto, nunca float/bool')
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f'{etiqueta}: importe invalido') from exc
    if not numero.is_finite():
        raise ValueError(f'{etiqueta}: importe no finito')
    return numero


def agregar(movimientos, *, escala_aprobada=None, regla_version=None):
    """Suma importes crudos por concepto y conserva líneas sin duplicarlas.

    Solo calcula COP cuando escala_aprobada y regla_version están explícitamente
    aprobadas por el llamador. No implica equivalencia con Excel ni certificación.
    """
    escala = None
    if escala_aprobada is not None:
        escala = _decimal(escala_aprobada, 'escala')
        if escala <= 0 or not regla_version:
            raise ValueError('Escala positiva y version de regla requeridas')
    acumulado = defaultdict(lambda: {'crudo': Decimal(0), 'lineas': [], 'claves': set()})
    pendientes = []
    for pos, fila in enumerate(movimientos, 1):
        if not isinstance(fila, dict):
            raise ValueError(f'Fila {pos}: estructura invalida')
        concepto = fila.get('concepto_verificado')
        archivo = fila.get('archivo_origen')
        linea = fila.get('linea_origen')
        if not archivo or not isinstance(linea, int) or linea < 1:
            raise ValueError(f'Fila {pos}: falta trazabilidad')
        if concepto not in CONCEPTOS or fila.get('clasificacion_aprobada') is not True:
            pendientes.append({'archivo_origen': archivo, 'linea_origen': linea,
                                'motivo': 'CLASIFICACION_NO_VERIFICADA'})
            continue
        clave = (str(archivo), linea)
        if clave in acumulado[concepto]['claves']:
            raise ValueError(f'Registro duplicado en {concepto}: {clave}')
        importe = _decimal(fila.get('importe_crudo'), f'fila {pos}')
        acumulado[concepto]['crudo'] += importe
        acumulado[concepto]['claves'].add(clave)
        acumulado[concepto]['lineas'].append({'archivo_origen': str(archivo), 'linea_origen': linea})
    resultados = []
    for concepto in sorted(acumulado):
        grupo = acumulado[concepto]
        resultados.append({
            'concepto': concepto, 'cantidad': len(grupo['claves']),
            'importe_crudo': str(grupo['crudo']),
            'importe_calculado': str(grupo['crudo'] / escala) if escala is not None else None,
            'escala_aplicada': str(escala) if escala is not None else None,
            'regla_version': regla_version if escala is not None else None,
            'estado': 'CALCULO_CON_PARAMETROS_NO_CERTIFICADO_EXCEL' if escala is not None else 'PENDIENTE_ESCALA',
            'lineas_origen': grupo['lineas'],
            'cuenta': None, 'debe': None, 'haber': None, 'neto': None,
            'diferencia': None, 'certificado_monetario': False,
        })
    return {'resultados': resultados, 'pendientes': pendientes,
            'certificado_monetario': False, 'valor_franquicia': None,
            'diferencia': None}
