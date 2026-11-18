"""Cobertura monetaria Credibanco: no sustituye aprobacion funcional.

Produce una fila por cuenta y evita interpretar la ausencia de evidencia como cero.
No escribe a bases de datos ni modifica los reportes existentes.
"""
from decimal import Decimal, InvalidOperation

CUENTAS = (
    '299095302', '299095408', '299095409', '196095001215',
    '196095001830', '196095001838', '196095001839', '196095001859',
    '196095001918', '299095882', '299095301', '299095300', '299095880',
)
FUENTES = frozenset(('HA22', 'HA26', 'HA32'))


def _importe(valor):
    if valor is None or isinstance(valor, bool):
        raise ValueError('Importe ausente o invalido')
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('Importe invalido') from exc
    if not numero.is_finite():
        raise ValueError('Importe no finito')
    return numero


def generar_cobertura(reglas, evidencias_franquicia, evidencias_host):
    """Solo compara evidencias explicitamente homologadas y aprobadas.

    Regla: cuenta, id_regla, estado='APROBADA', fuente_host, concepto,
    fecha_contable, signo (1/-1). Evidencias: cuenta, concepto, fecha_contable,
    id_archivo, id_registro, valor (franquicia) / debe, haber, fuente_host (Host).
    Las fuentes no se agregan entre si. Multiples reglas por cuenta se bloquean.
    """
    reglas = list(reglas)
    fran = list(evidencias_franquicia)
    host = list(evidencias_host)
    salida = []
    for cuenta in CUENTAS:
        candidatas = [r for r in reglas if str(r.get('cuenta')) == cuenta]
        base = dict(cuenta=cuenta, valor_franquicia=None, neto_host=None,
                    diferencia=None, certificado=False, id_regla=None)
        if len(candidatas) != 1:
            salida.append({**base, 'estado': 'SIN_REGLA_APROBADA' if not candidatas else 'REGLAS_AMBIGUAS'})
            continue
        r = candidatas[0]
        base['id_regla'] = r.get('id_regla')
        if (r.get('estado') != 'APROBADA' or r.get('fuente_host') not in FUENTES
                or r.get('signo') not in (1, -1) or isinstance(r.get('signo'), bool)
                or not all(r.get(k) for k in ('id_regla', 'concepto', 'fecha_contable'))):
            salida.append({**base, 'estado': 'REGLA_INCOMPLETA_O_NO_APROBADA'})
            continue
        fecha = str(r['fecha_contable'])
        origen = [e for e in fran if str(e.get('cuenta')) == cuenta
                  and e.get('concepto') == r['concepto'] and str(e.get('fecha_contable')) == fecha]
        contraparte = [e for e in host if str(e.get('cuenta')) == cuenta
                       and e.get('fuente_host') == r['fuente_host']
                       and str(e.get('fecha_contable')) == fecha]
        if not origen or not contraparte:
            salida.append({**base, 'estado': 'SIN_EVIDENCIA_FRANQUICIA' if not origen else 'SIN_EVIDENCIA_HOST'})
            continue
        todos = origen + contraparte
        claves = [(e.get('id_archivo'), e.get('id_registro')) for e in todos]
        if any(not a or not b for a, b in claves) or len(set(claves)) != len(claves):
            salida.append({**base, 'estado': 'TRAZABILIDAD_INCOMPLETA'})
            continue
        try:
            vf = sum((_importe(e.get('valor')) for e in origen), Decimal(0)) * r['signo']
            nh = sum((_importe(e.get('debe')) - _importe(e.get('haber')) for e in contraparte), Decimal(0))
        except ValueError:
            salida.append({**base, 'estado': 'IMPORTE_INCOMPLETO'})
            continue
        salida.append({**base, 'valor_franquicia': str(vf), 'neto_host': str(nh),
                       'diferencia': str(vf - nh), 'fuente_host': r['fuente_host'],
                       'estado': 'COINCIDE_CALCULO_NO_CERTIFICADO' if vf == nh else 'DIFERENCIA_CALCULO_NO_CERTIFICADO',
                       'evidencias_franquicia': len(origen), 'evidencias_host': len(contraparte)})
    return {'franquicia': 'CREDIBANCO', 'total_cuentas': len(CUENTAS),
            'certificado': False, 'filas': salida}
