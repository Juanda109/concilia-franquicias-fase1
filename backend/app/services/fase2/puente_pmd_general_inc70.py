"""Puente de solo lectura entre PMD General Entidad persistido y motor INC70."""
from collections import Counter
from decimal import Decimal
from app.services.fase2.motor_desagregacion_redeban import MEDIDAS, decimal_seguro, validar_desagregacion


def verificar_pmd_general(cruce, matriz, filas_pmd):
    if cruce.get('id_jornada') != matriz.get('id_jornada'):
        raise ValueError('Jornadas incompatibles')
    if cruce.get('certificado') is not False or matriz.get('certificado') is not False:
        raise ValueError('Certificacion inesperada')
    ids = {g['padre'] for g in cruce['grupos']}
    if len(ids) != len(cruce['grupos']):
        raise ValueError('Padres duplicados')
    por_nivel = {}
    for f in filas_pmd:
        if f.get('ES_CONTROL'):
            continue
        nivel = str(f.get('NIVEL') or '').strip()
        por_nivel.setdefault(nivel, []).append(f)
    detalle = []
    for g in cruce['grupos']:
        nivel = g['padre']
        candidatas = por_nivel.get(nivel, [])
        referencias = g.get('registros_pmd_reales', [])
        estado = 'NIVEL_NO_UNICO_O_AUSENTE'
        diferencias = {}
        if len(candidatas) == len(referencias) == 1:
            actual = candidatas[0]
            referencia = referencias[0]
            if str(actual.get('id_archivo')) != str(referencia.get('id_archivo')) or str(actual.get('numero_linea')) != str(referencia.get('linea_pmd')):
                estado = 'ORIGEN_DIFERENTE'
            else:
                for medida in MEDIDAS:
                    valor = decimal_seguro(actual.get(medida))
                    esperado = decimal_seguro(referencia['medidas'][medida])
                    if valor != esperado:
                        diferencias[medida] = {'persistido': str(valor), 'evidencia': str(esperado)}
                estado = 'PMD_VERIFICADO_SIN_DESGLOSE' if not diferencias else 'IMPORTE_DIFERENTE'
        detalle.append({'padre': nivel, 'operaciones': g['operaciones'], 'estado': estado,
                        'diferencias': diferencias, 'homologado': False})
    return {'id_jornada': cruce['id_jornada'], 'grupos': detalle,
            'resumen': dict(Counter(g['estado'] for g in detalle)),
            'certificado': False, 'advertencia': 'Verificacion de fuente agregada; no distribuye importes a hijas.'}


def diagnosticar_sin_asignaciones(cruce, matriz, filas_pmd):
    fuente = verificar_pmd_general(cruce, matriz, filas_pmd)
    control = validar_desagregacion(cruce, matriz, [], aprobaciones={})
    if control['homologados'] != 0:
        raise ValueError('Homologacion no autorizada')
    return {'fuente_pmd_general': fuente, 'control_desagregacion': control, 'certificado': False}
