"""INC56-H3: cruce DEPO/Host solo con correspondencias aprobadas.

No lee Excel ni SQL, no infiere cuentas, escala, signo o fuente.
La salida siempre es NO CERTIFICADA: las aprobaciones son entradas externas
que deben respaldarse documentalmente antes de uso productivo.
"""
from decimal import Decimal, InvalidOperation

CUENTAS_PERMITIDAS = frozenset({'196095001838', '196095001839'})
NATURALEZAS = frozenset({'D', 'H'})


def _numero(valor):
    if isinstance(valor, (bool, float)):
        raise ValueError('Importe flotante o booleano no permitido')
    try:
        resultado = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('Importe invalido') from exc
    if not resultado.is_finite():
        raise ValueError('Importe no finito')
    return resultado


def cruzar(agregados_depo, sumatorias_host, *, fuente_host=None,
           correspondencias_aprobadas=None, regla_neto=None):
    """Recibe resultado INC56-G y sumatorias INC56-E de UNA fuente Host.

    correspondencias_aprobadas: {concepto: {cuenta, naturaleza,
      aprobada: True, regla_version: str}}.
    regla_neto: {'aprobada': True, 'regla_version': str,
                 'expresion': 'DEBE_MENOS_HABER'}.
    Una correspondencia permite mostrar una comparacion de prueba, no certificar.
    """
    if not isinstance(agregados_depo, dict) or not isinstance(sumatorias_host, list):
        raise ValueError('Contratos de entrada invalidos')
    correspondencias = correspondencias_aprobadas or {}
    if not isinstance(correspondencias, dict):
        raise ValueError('Correspondencias invalidas')
    if sumatorias_host and fuente_host not in ('HA22', 'HA26', 'HA32'):
        raise ValueError('Seleccionar una fuente Host explicita')
    host = {}
    for fila in sumatorias_host:
        clave = (str(fila['cuenta']).strip(), str(fila['naturaleza']).upper())
        if clave in host:
            raise ValueError('Sumatoria Host duplicada')
        if clave[0] not in CUENTAS_PERMITIDAS or clave[1] not in NATURALEZAS:
            raise ValueError('Cuenta o naturaleza Host no soportada')
        host[clave] = _numero(fila['importe_contable'])
    neto_aprobado = (isinstance(regla_neto, dict)
                     and regla_neto.get('aprobada') is True
                     and str(regla_neto.get('regla_version') or '').strip()
                     and regla_neto.get('expresion') == 'DEBE_MENOS_HABER')
    resultados = []
    conceptos = [fila['concepto'] for fila in agregados_depo.get('resultados', [])]
    if len(conceptos) != len(set(conceptos)):
        raise ValueError('Concepto DEPO duplicado')
    if set(correspondencias) - set(conceptos):
        raise ValueError('Correspondencia sin concepto DEPO')
    for fila in agregados_depo.get('resultados', []):
        concepto = fila['concepto']
        aprobacion = correspondencias.get(concepto)
        cuenta = naturaleza = valor_host = diferencia = None
        estado = 'PENDIENTE_CORRESPONDENCIA'
        if aprobacion is not None:
            if not isinstance(aprobacion, dict) or aprobacion.get('aprobada') is not True or not str(aprobacion.get('regla_version') or '').strip():
                raise ValueError('Correspondencia sin aprobacion/version')
            cuenta = str(aprobacion.get('cuenta'))
            naturaleza = str(aprobacion.get('naturaleza')).upper()
            if cuenta not in CUENTAS_PERMITIDAS or naturaleza not in NATURALEZAS:
                raise ValueError('Cuenta/naturaleza no soportada')
            if (cuenta, naturaleza) in host:
                valor_host = host[(cuenta, naturaleza)]
                estado = 'PENDIENTE_ESCALA_O_REGLA_NETO'
            else:
                estado = 'SIN_MOVIMIENTO_HOST'
        importe = fila.get('importe_calculado')
        if (importe is not None and valor_host is not None and neto_aprobado
                and fila.get('escala_aplicada') is not None
                and str(fila.get('regla_version') or '').strip()):
            # Comparacion aritmetica de prueba, no conciliacion certificada.
            diferencia = _numero(importe) - valor_host
            estado = 'COMPARACION_DIAGNOSTICA_NO_CERTIFICADA'
        resultados.append({
            'concepto': concepto, 'cuenta': cuenta, 'naturaleza': naturaleza,
            'valor_franquicia': importe if importe is not None else None,
            'valor_host': str(valor_host) if valor_host is not None else None,
            'diferencia_diagnostica': str(diferencia) if diferencia is not None else None,
            'debe_host': str(host[(cuenta, 'D')]) if cuenta and (cuenta, 'D') in host else None,
            'haber_host': str(host[(cuenta, 'H')]) if cuenta and (cuenta, 'H') in host else None,
            'neto_host': str(host[(cuenta, 'D')] - host[(cuenta, 'H')]) if cuenta and neto_aprobado and (cuenta, 'D') in host and (cuenta, 'H') in host else None,
            'lineas_origen': list(fila.get('lineas_origen') or []),
            'estado': estado, 'certificado_monetario': False,
        })
    return {'fuente_host': fuente_host, 'resultados': resultados,
            'certificado_monetario': False, 'diferencia': None,
            'estado': 'DIAGNOSTICO_NO_CERTIFICADO',
            'advertencia': 'Cruce de prueba; sin equivalencia contable certificada.'}
