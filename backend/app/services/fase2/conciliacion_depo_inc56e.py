"""INC56-E: reproducir exclusivamente SUMIFS D2:D5 sobre movimientos contables provistos.

No transforma DEPO crudo en COP, ni asigna cuentas, ni calcula diferencias.
"""
from decimal import Decimal, InvalidOperation

CUENTAS = ('196095001838', '196095001839')
NATURALEZAS = ('D', 'H')
CELDAS = {('196095001838','D'):'D2',('196095001838','H'):'D3',
          ('196095001839','D'):'D4',('196095001839','H'):'D5'}


def sumar_contabilidad(movimientos):
    """Recibe iterable de dicts con cuenta, naturaleza, importe (unidades ya contables).

    No modifica registros; no deduce signos ni escalas.
    """
    totales = {(c,n):Decimal('0') for c in CUENTAS for n in NATURALEZAS}
    evidencia = {(c,n):[] for c in CUENTAS for n in NATURALEZAS}
    for idx, fila in enumerate(movimientos, start=1):
        cuenta = str(fila['cuenta']).strip()
        naturaleza = str(fila['naturaleza']).strip().upper()
        if (cuenta,naturaleza) not in totales:
            continue
        try:
            importe = Decimal(str(fila['importe']))
        except (InvalidOperation, TypeError) as exc:
            raise ValueError(f'Importe invalido en fila {idx}') from exc
        if not importe.is_finite():
            raise ValueError(f'Importe no finito en fila {idx}')
        totales[(cuenta,naturaleza)] += importe
        evidencia[(cuenta,naturaleza)].append(fila.get('linea_origen',idx))
    return [{'celda_excel':CELDAS[(c,n)],'cuenta':c,'naturaleza':n,
             'importe_contable':str(totales[(c,n)]),
             'lineas_origen':evidencia[(c,n)],
             'estado':'SUMIFS_REPRODUCIDO_SIN_HOMOLOGACION_DEPO'}
            for c in CUENTAS for n in NATURALEZAS]


def estado_depo():
    return {'certificado_monetario':False, 'valor_franquicia':None,
            'diferencia':None, 'debe_depo':None, 'haber_depo':None,
            'estado':'PENDIENTE_ESCALA_PIVOT_Y_CORRESPONDENCIA'}
