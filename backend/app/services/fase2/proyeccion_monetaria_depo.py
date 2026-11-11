"""Proyeccion monetaria DEPO: reemplaza calculos Excel en ejecucion.

Separa evidencia cruda, contabilidad Host y conciliacion certificada.
No asume escala, signo, correspondencia o igualdad entre fuentes.
"""
from decimal import Decimal, InvalidOperation

CUENTAS = {
    '017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS': '196095001838',
    '017-VR. DEPOSITOS ELECTRONICOS INTERNACIONAL CONSIGNADOS': '196095001839',
}
FUENTES = frozenset({'HA22', 'HA26', 'HA32'})


def _decimal(value):
    if value is None or isinstance(value, (bool, float)):
        raise ValueError('Importe ausente o no exacto')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Importe no decimal') from exc
    if not result.is_finite():
        raise ValueError('Importe no finito')
    return result


def proyectar_depo(categorias, sumatorias_host, *, aprobacion=None):
    """Calcula importes DEPO en Python, sin Excel.

    aprobacion opcional y explicita: {'version':str,'escala':str,
    'conceptos': {concepto:{'cuenta':str,'naturaleza': 'D'|'H'}},
    'regla_neto':'DEBE_MENOS_HABER'}.
    No certifica conciliacion: requiere contraste externo aprobado.
    """
    categorias = categorias or []
    sumatorias_host = sumatorias_host or []
    if not isinstance(categorias, list) or not isinstance(sumatorias_host, list):
        raise ValueError('Estructura de entrada invalida')
    escala = None
    version = None
    mapeos = {}
    if aprobacion is not None:
        if not isinstance(aprobacion, dict) or not str(aprobacion.get('version') or '').strip():
            raise ValueError('Aprobacion versionada requerida')
        version = str(aprobacion['version'])
        escala = _decimal(aprobacion.get('escala'))
        if escala <= 0:
            raise ValueError('Escala positiva requerida')
        if aprobacion.get('regla_neto') != 'DEBE_MENOS_HABER':
            raise ValueError('Regla neto explicita requerida')
        mapeos = aprobacion.get('conceptos') or {}
        if not isinstance(mapeos, dict):
            raise ValueError('Catalogo de correspondencias invalido')
    host = {}
    for fila in sumatorias_host:
        fuente = fila['fuente_host']
        cuenta = str(fila['cuenta']).strip()
        naturaleza = fila['naturaleza']
        if fuente not in FUENTES or naturaleza not in ('D', 'H'):
            raise ValueError('Fuente o naturaleza Host no valida')
        key = (fuente, cuenta, naturaleza)
        if key in host:
            raise ValueError('Sumatoria Host duplicada')
        host[key] = _decimal(fila['importe_contable'])
    resultado = []
    for fila in categorias:
        concepto = str(fila['concepto'])
        crudo = fila.get('valor_total_crudo')
        cantidad = fila.get('cantidad')
        invalidos = fila.get('registros_sin_valor', 0)
        if type(cantidad) is not int or cantidad < 0 or type(invalidos) is not int or invalidos < 0:
            raise ValueError('Contadores invalidos')
        if crudo is not None:
            numero = _decimal(crudo)
            if numero < 0:
                raise ValueError('Crudo negativo inesperado')
        else:
            numero = None
        mapping = mapeos.get(concepto)
        cuenta = CUENTAS.get(concepto)
        calculado = None
        if mapping is not None:
            if concepto not in CUENTAS or not isinstance(mapping, dict) or mapping.get('cuenta') != cuenta or mapping.get('naturaleza') not in ('D', 'H'):
                raise ValueError('Correspondencia no autorizada')
            if numero is not None and invalidos == 0:
                calculado = str(numero / escala)
        resultado.append({
            'concepto': concepto, 'cuenta_referencia': cuenta,
            'cantidad': cantidad, 'valor_total_crudo': str(numero) if numero is not None else None,
            'unidad_cruda': 'UNIDADES_CRUDAS', 'registros_sin_valor': invalidos,
            'importe_calculado_no_certificado': calculado,
            'version_regla': version if calculado is not None else None,
            'valor_franquicia_certificado': None, 'diferencia_certificada': None,
            'certificado_monetario': False,
            'lineas_origen': list(fila.get('lineas_origen') or []),
        })
    evidencia_host = [
        {'fuente_host': f, 'cuenta': c, 'debe': str(host[(f,c,'D')]) if (f,c,'D') in host else None,
         'haber': str(host[(f,c,'H')]) if (f,c,'H') in host else None,
         'neto_diagnostico': None}
        for f in ('HA22','HA26','HA32') for c in CUENTAS.values()
    ]
    return {'categorias': resultado, 'evidencia_host': evidencia_host,
            'certificado_monetario': False,
            'estado': 'PENDIENTE_CERTIFICACION_ESCALA_Y_EQUIVALENCIA' if aprobacion is None else 'CALCULO_VERSIONADO_NO_CERTIFICADO'}
