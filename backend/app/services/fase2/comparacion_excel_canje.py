"""Comparacion F2 CAET/CANT vs referencia validada de Excel. Sin E/S DB."""
from collections import Counter
from decimal import Decimal, InvalidOperation

KEYS = ('tipo_insumo', 'cuenta', 'tipo_tarjeta', 'canal', 'tx')
METRICS = ('cantidad', 'vl_total', 'vl_interc', 'comision_op_exitosas', 'tii_recibida')


def _number(value, field):
    if isinstance(value, (float, bool)) or value is None:
        raise ValueError(f'{field}: valor numerico invalido')
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'{field}: valor no numerico') from exc
    if not result.is_finite():
        raise ValueError(f'{field}: valor no finito')
    if field == 'cantidad' and (result < 0 or result != result.to_integral_value()):
        raise ValueError('cantidad debe ser entero no negativo')
    return result


def _index(rows, label):
    index = {}
    for n, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f'{label} fila {n}: formato invalido')
        missing = set(KEYS + METRICS) - set(row)
        if missing:
            raise ValueError(f'{label} fila {n}: faltan {sorted(missing)}')
        key = tuple(str(row[k]).strip() for k in KEYS)
        if not key[0] in ('CAET', 'CANT') or not all(key):
            raise ValueError(f'{label} fila {n}: llave invalida')
        if key in index:
            raise ValueError(f'{label}: grupo duplicado {key}')
        index[key] = {m: _number(row[m], m) for m in METRICS}
    return index


def comparar_grupos(calculados, esperados, tolerancia='0'):
    """Comparacion exacta por llave, con tolerancia monetaria explicita.

    La cantidad siempre debe coincidir exactamente. Los faltantes y sobrantes
    son diferencias aunque sus importes sean cero.
    """
    tol = _number(tolerancia, 'tolerancia')
    if tol < 0:
        raise ValueError('tolerancia no puede ser negativa')
    a, e = _index(calculados, 'calculado'), _index(esperados, 'referencia')
    diferencias = []
    for key in sorted(set(a) | set(e)):
        if key not in a or key not in e:
            diferencias.append({'clave': dict(zip(KEYS, key)),
                                'estado': 'FALTA_CALCULADO' if key not in a else 'SOBRA_CALCULADO'})
            continue
        for metric in METRICS:
            delta = a[key][metric] - e[key][metric]
            if (delta != 0 if metric == 'cantidad' else abs(delta) > tol):
                diferencias.append({'clave': dict(zip(KEYS, key)), 'estado': 'DIFERENCIA',
                                    'campo': metric, 'calculado': str(a[key][metric]),
                                    'esperado': str(e[key][metric]), 'delta': str(delta)})
    return {'coincide': not diferencias, 'grupos_calculados': len(a),
            'grupos_referencia': len(e), 'tolerancia': str(tol),
            'diferencias': diferencias}
