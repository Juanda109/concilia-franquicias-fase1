"""INC56-H2: clasificacion explicita de movimientos DEPO sin Excel ni SQL."""
from app.services.fase2.motor_monetario_depo_inc56g import CONCEPTOS


def construir_clasificados(archivo, extraidos, aprobaciones):
    """Las aprobaciones se indexan por numero de linea y no se infieren de BIN.

    Cada aprobacion requiere concepto, version, importe y coincidencia con el
    valor crudo extraido. Nunca homologa una cuenta ni certifica conciliacion.
    """
    if not isinstance(aprobaciones, dict):
        raise ValueError('Aprobaciones deben ser un diccionario')
    indices = {fila['numero_linea'] for fila in extraidos}
    if any(type(k) is not int or k not in indices for k in aprobaciones):
        raise ValueError('Aprobacion para linea inexistente o invalida')
    resultado, pendientes = [], []
    for fila in extraidos:
        n = fila['numero_linea']
        aprobacion = aprobaciones.get(n)
        if aprobacion is None:
            pendientes.append({'archivo_origen':archivo, 'linea_origen':n,
                               'motivo':'CLASIFICACION_NO_APROBADA'})
            continue
        if not isinstance(aprobacion, dict) or aprobacion.get('clasificacion_aprobada') is not True:
            raise ValueError(f'Linea {n}: aprobacion explicita requerida')
        concepto = aprobacion.get('concepto_verificado')
        if concepto not in CONCEPTOS:
            raise ValueError(f'Linea {n}: concepto no soportado')
        if not str(aprobacion.get('regla_version') or '').strip():
            raise ValueError(f'Linea {n}: falta version de regla')
        if fila['TIPO_MOVIMIENTO'] == '05':
            raise ValueError(f'Linea {n}: control resumen no clasificable')
        raw = fila.get('VALOR_TOTAL_CRUDO')
        if raw is None or raw != aprobacion.get('importe_crudo'):
            raise ValueError(f'Linea {n}: importe crudo no coincide')
        resultado.append({'concepto_verificado':concepto,
                          'clasificacion_aprobada':True,
                          'archivo_origen':archivo, 'linea_origen':n,
                          'importe_crudo':raw})
    return resultado, pendientes
