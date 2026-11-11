"""INC52: adaptador de desglose Host. No homologa ni consolida fuentes."""
from decimal import Decimal, InvalidOperation

FUENTES_HOST = ('HA22', 'HA26', 'HA32')

def _importe(valor):
    if valor is None:
        return None
    try:
        return str(Decimal(str(valor)))
    except (InvalidOperation, ValueError):
        raise ValueError('Importe Host invalido')

def desglose_host(fila):
    """Devuelve filas por fuente/archivo, sin sumar ni duplicar por concepto."""
    cuenta = str(fila.get('cuenta') or '')
    diag = fila.get('host_diagnostico_inc50') or {}
    fuentes = diag.get('fuentes') or {}
    salida = []
    for fuente in FUENTES_HOST:
        for registro in fuentes.get(fuente) or []:
            if str(registro.get('cuenta') or '') != cuenta:
                raise ValueError('Cuenta Host distinta de fila maestra')
            debe = _importe(registro.get('debe'))
            haber = _importe(registro.get('haber'))
            neto = _importe(registro.get('neto_diagnostico'))
            if debe is not None and haber is not None and neto is not None:
                if Decimal(debe) - Decimal(haber) != Decimal(neto):
                    raise ValueError('Neto Host inconsistente')
            salida.append({'fuente': fuente, 'cuenta': cuenta,
                'centro': registro.get('centro'), 'id_archivo': registro.get('id_archivo'),
                'lineas_origen': registro.get('lineas_origen') or [],
                'debe': debe, 'haber': haber, 'neto_diagnostico': neto,
                'saldo_inicial': None, 'saldo_inicial_estado': 'NO_DISPONIBLE_EN_INC50' if fuente == 'HA32' else 'NO_APLICA',
                'estado': 'DIAGNOSTICO_NO_HOMOLOGADO',
                'advertencia': 'No sumar fuentes ni conceptos por cuenta sin regla aprobada.'})
    return salida

def desglose_host_unico(filas):
    """Deduplica presentaciones repetidas por concepto sin ocultar movimientos distintos."""
    vistos = {}
    for fila in filas:
        for registro in desglose_host(fila):
            clave = (registro['fuente'], registro['id_archivo'], registro['cuenta'],
                     registro['centro'], tuple(registro['lineas_origen']))
            if clave in vistos and vistos[clave] != registro:
                raise ValueError('Conflicto de datos para la misma procedencia Host')
            vistos[clave] = registro
    return list(vistos.values())
