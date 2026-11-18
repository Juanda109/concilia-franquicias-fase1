"""INC67: comparacion monetaria diagnostica aislada, sin acceso a BD."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

REGLAS_PENDIENTES = {'SIN_REGLA_FECHA', 'VALIDAR_REFERENCIA'}


def _decimal(valor):
    if valor is None or isinstance(valor, bool) or isinstance(valor, float):
        raise ValueError('Importe ausente o de tipo no exacto')
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Importe invalido') from exc
    if not numero.is_finite():
        raise ValueError('Importe no finito')
    return numero


def comparar(catalogo, homologaciones, redeban, host, fecha_jornada, reglas_fecha_validadas=None, signo_host=None):
    """Compara importes solo si fecha, correspondencia y signo estan validados.

    Entradas: redeban [{cuenta, importe, fila_excel, estado}], host
    [{cuenta, debe, haber, fuente, linea, fecha_contable, centro, sintetico}].
    La fecha se autoriza explicitamente por cuenta en reglas_fecha_validadas:
    {cuenta: {fechas ISO}}. El signo se autoriza por cuenta en signo_host:
    {cuenta: 'DEBE_MENOS_HABER'|'HABER_MENOS_DEBE'}.
    """
    reglas_fecha_validadas = reglas_fecha_validadas or {}
    signo_host = signo_host or {}
    if set(catalogo) != set(homologaciones):
        raise ValueError('Catalogo y homologaciones incompatibles')
    r_por = defaultdict(list)
    h_por = defaultdict(list)
    pendientes_por = defaultdict(list)
    for fila in redeban:
        cuenta = str(fila.get('cuenta') or fila.get('cuenta_contable') or '').strip()
        if cuenta in catalogo and fila.get('estado') == 'OPERANDOS_NO_RESUELTOS':
            pendientes_por[cuenta].append(fila.get('fila_excel'))
        if cuenta in catalogo and fila.get('estado') == 'CALCULO_DIAGNOSTICO':
            importe = fila.get('importe', fila.get('neto_diagnostico'))
            if importe is not None:
                r_por[cuenta].append((fila, _decimal(importe)))
    for fila in host:
        cuenta = str(fila.get('cuenta') or fila.get('NUCTA') or '').strip()
        centro = str(fila.get('centro') or fila.get('CEDESTIN') or '').strip()
        if cuenta in catalogo and centro in ('17', '0017'):
            h_por[cuenta].append(fila)
    salida = []
    for cuenta in sorted(catalogo):
        homologacion = homologaciones[cuenta]
        franquicias = str(homologacion.get('franquicia_relacionada') or '').upper().split('|')
        if 'REDEBAN' not in franquicias:
            continue
        r = r_por[cuenta]
        h = h_por[cuenta]
        base = {'cuenta': cuenta, 'fecha_jornada': str(fecha_jornada),
                'regla_fecha': catalogo[cuenta].get('regla_consulta'),
                'filas_redeban': [x.get('fila_excel') for x, _ in r],
                'host_origen': [{'fuente': x.get('fuente') or x.get('TX_ORIGEN'), 'linea': x.get('linea') or x.get('numero_linea')} for x in h],
                'cantidad_redeban': len(r), 'cantidad_redeban_pendientes': len(pendientes_por[cuenta]),
                'filas_redeban_pendientes': pendientes_por[cuenta], 'cantidad_host': len(h),
                'neto_redeban': None, 'neto_host': None, 'diferencia': None,
                'certificado': False}
        if pendientes_por[cuenta]:
            estado = 'PENDIENTE_OPERANDOS_REDEBAN'
        elif not r:
            estado = 'SIN_REDEBAN'
        elif not h:
            estado = 'SIN_HOST'
        elif catalogo[cuenta].get('regla_consulta') in REGLAS_PENDIENTES or cuenta not in reglas_fecha_validadas:
            estado = 'PENDIENTE_REGLA_FECHA'
        elif not all(str(x.get('fecha_contable') or x.get('FECON') or x.get('FECONT')) in reglas_fecha_validadas[cuenta] for x in h):
            estado = 'PENDIENTE_REGLA_FECHA'
        elif any(x.get('sintetico') is True or 'PRUEBA' in str(x.get('DESCON') or '').upper()
                 or 'PRUEBA' in str(x.get('campos_origen') or '').upper() for x in h):
            estado = 'SOLO_PRUEBA_SINTETICA'
        elif len({str(x.get('fuente') or x.get('TX_ORIGEN')) for x in h}) != 1:
            estado = 'PENDIENTE_FUENTE_HOST'
        elif cuenta not in signo_host or homologacion.get('estado_homologacion') != 'HOMOLOGADA_MONETARIA':
            estado = 'PENDIENTE_HOMOLOGACION'
        else:
            signo = signo_host[cuenta]
            if signo not in ('DEBE_MENOS_HABER', 'HABER_MENOS_DEBE'):
                raise ValueError('Convencion de signo invalida')
            nr = sum((importe for _, importe in r), Decimal(0))
            nh = Decimal(0)
            for x in h:
                debe, haber = _decimal(x.get('debe', x.get('DEBE'))), _decimal(x.get('haber', x.get('HABER')))
                nh += debe - haber if signo == 'DEBE_MENOS_HABER' else haber - debe
            base.update(neto_redeban=str(nr), neto_host=str(nh), diferencia=str(nr-nh))
            estado = 'CONCILIACION_DIAGNOSTICA'
        base['estado'] = estado
        salida.append(base)
    return {'estado': 'DIAGNOSTICO_NO_CERTIFICADO', 'certificado': False, 'cuentas': salida}
