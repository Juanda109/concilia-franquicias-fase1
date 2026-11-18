"""Motor de validacion de desagregacion Redeban: nunca infiere asignaciones."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

MEDIDAS = ('DEBITO_VALOR', 'CREDITO_VALOR', 'DEBITO_COMISION_INTERCAMBIO',
           'CREDITO_COMISION_INTERCAMBIO', 'DEBITO_COMISION_ADMINISTRATIVA',
           'CREDITO_COMISION_ADMINISTRATIVA')


def decimal_seguro(valor):
    if valor is None or isinstance(valor, bool):
        raise ValueError('Importe ausente o invalido')
    try:
        resultado = Decimal(str(valor))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Importe no numerico') from exc
    if not resultado.is_finite():
        raise ValueError('Importe no finito')
    return resultado


def validar_desagregacion(cruce, matriz, asignaciones, *, aprobaciones=None):
    """Comprueba integridad y conservacion por padre y medida.

    asignaciones: [{padre, fila_excel, medida, importe, id_evidencia,
                    id_regla, fecha_contable, fuente, id_transaccion}].
    aprobaciones: dict padre -> {id_regla, evidencia_exclusividad,
                                 fecha_contable, fuente, aprobado: bool}.
    Sin aprobacion explicita se emite solo diagnostico, no homologacion.
    """
    aprobaciones = aprobaciones or {}
    if cruce.get('id_jornada') != matriz.get('id_jornada'):
        raise ValueError('Jornadas incompatibles')
    if cruce.get('certificado') is not False or matriz.get('certificado') is not False:
        raise ValueError('Fuente certificada inesperada')
    grupos = cruce['grupos']
    indice = {g['padre']: g for g in grupos}
    if len(indice) != len(grupos):
        raise ValueError('Padres repetidos')
    pendientes = {int(f['fila_excel']): f for f in matriz['matriz']}
    if len(pendientes) != len(matriz['matriz']):
        raise ValueError('Filas Excel repetidas')
    agrupadas = defaultdict(list)
    usados = set()
    for a in asignaciones:
        padre, fila, medida = a['padre'], int(a['fila_excel']), a['medida']
        if padre not in indice or fila not in pendientes or fila not in indice[padre]['filas_excel']:
            raise ValueError('Asignacion fuera de grupo')
        if medida not in MEDIDAS:
            raise ValueError('Medida no autorizada')
        if not all(a.get(c) for c in ('id_evidencia', 'id_regla', 'fecha_contable', 'fuente', 'id_transaccion')):
            raise ValueError('Trazabilidad incompleta')
        if a['fecha_contable'] != '2026-10-02':
            raise ValueError('Fecha incompatible con jornada 6466')
        clave = (a['fuente'], a['id_transaccion'], medida)
        if clave in usados:
            raise ValueError('Transaccion/medida asignada mas de una vez')
        usados.add(clave)
        agrupadas[(padre, medida)].append((fila, decimal_seguro(a['importe']), a))
    decisiones = []
    for padre, grupo in sorted(indice.items()):
        registros = grupo.get('registros_pmd_reales', [])
        if len(registros) != 1:
            decisiones.append({'padre': padre, 'estado': 'FUENTE_PMD_NO_UNICA', 'homologado': False})
            continue
        medidas_pmd = registros[0]['medidas']
        reglas = aprobaciones.get(padre, {})
        verificaciones = []
        for medida in MEDIDAS:
            entradas = agrupadas.get((padre, medida), [])
            total = sum((x[1] for x in entradas), Decimal('0'))
            esperado = decimal_seguro(medidas_pmd[medida])
            filas = {x[0] for x in entradas}
            verificaciones.append({'medida': medida, 'importe_pmd': str(esperado),
                                   'importe_asignado': str(total), 'diferencia': str(esperado-total),
                                   'filas_cubiertas': len(filas), 'conserva': total == esperado,
                                   'cobertura_completa': filas == set(grupo['filas_excel'])})
        evidencia_aprobada = (reglas.get('aprobado') is True and
                              bool(reglas.get('id_regla')) and
                              bool(reglas.get('evidencia_exclusividad')) and
                              reglas.get('fecha_contable') == '2026-10-02' and
                              bool(reglas.get('fuente')))
        completo = all(v['conserva'] and v['cobertura_completa'] for v in verificaciones)
        homologado = bool(evidencia_aprobada and completo)
        decisiones.append({'padre': padre, 'operaciones': grupo['operaciones'],
                           'estado': 'VALIDADO_CON_EVIDENCIA' if homologado else
                           'PENDIENTE_EVIDENCIA_O_DESGLOSE',
                           'homologado': homologado, 'medidas': verificaciones})
    return {'id_jornada': cruce['id_jornada'], 'grupos': decisiones,
            'homologados': sum(x['homologado'] for x in decisiones),
            'certificado': False, 'advertencia': 'Diagnostico: no certifica conciliacion Redeban-Host.'}
