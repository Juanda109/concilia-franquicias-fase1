"""Auditoria de operandos Redeban basada en PMD real; sin certificacion."""
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

from app.services.fase2.formulas_redeban_inc60 import MEDIDAS
from app.services.fase2.motor_pmd_inc58 import buscar_nivel


def _causa_operandos(fila, filas_pmd):
    categoria = fila.get('categoria')
    if categoria not in MEDIDAS:
        return 'CATEGORIA_NO_ESTANDAR', {}
    codigo = fila.get('codigo_operacion')
    if not codigo:
        return 'CODIGO_AUSENTE', {}
    medidas = MEDIDAS[categoria]
    detalle = {}
    causas = []
    for lado in ('debito', 'credito'):
        medida = medidas[lado]
        dato = buscar_nivel(filas_pmd, codigo, medida)
        estado = dato['estado']
        if estado == 'ENCONTRADO' and dato.get('valor') is None:
            estado = 'VALOR_AUSENTE'
        detalle[lado] = {
            'medida': medida, 'nivel_buscado': str(codigo),
            'estado': estado, 'lineas_origen': dato.get('lineas_origen', []),
        }
        if estado != 'ENCONTRADO':
            causas.append(f'{lado.upper()}:{estado}')
    if not causas:
        return 'INCONSISTENCIA_ESTADO_CALCULABLE', detalle
    return '|'.join(causas), detalle


def auditar(detalle, cuentas_autorizadas, filas_pmd=None):
    """Con filas_pmd analiza causas reales; sin ellas informa SIN_DIAGNOSTICO."""
    cuentas = set(map(str, cuentas_autorizadas))
    grupos = defaultdict(lambda: {
        'filas': 0, 'calculadas': 0, 'pendientes': 0,
        'causas': Counter(), 'neto_parcial': Decimal('0'),
        'ejemplos': defaultdict(list),
    })
    globales = Counter()
    pendientes_detalle = []
    for fila in detalle:
        cuenta = str(fila.get('cuenta_contable') or '').strip()
        estado = fila.get('estado')
        globales[estado] += 1
        if cuenta not in cuentas:
            continue
        grupo = grupos[cuenta]
        grupo['filas'] += 1
        if estado == 'CALCULO_DIAGNOSTICO':
            valor = fila.get('neto_diagnostico')
            if valor is None or isinstance(valor, (float, bool)):
                raise ValueError('Neto calculado invalido')
            try:
                numero = Decimal(str(valor))
            except InvalidOperation as exc:
                raise ValueError('Neto calculado invalido') from exc
            if not numero.is_finite():
                raise ValueError('Neto no finito')
            grupo['calculadas'] += 1
            grupo['neto_parcial'] += numero
        elif estado == 'OPERANDOS_NO_RESUELTOS':
            grupo['pendientes'] += 1
            calculo = fila.get('calculo')
            if filas_pmd is not None:
                causa, operandos = _causa_operandos(fila, filas_pmd)
            elif isinstance(calculo, dict) and calculo:
                causas = []
                operandos = calculo
                for lado in ('debito', 'credito'):
                    dato = calculo.get(lado) or {}
                    estado_operando = dato.get('estado') or 'SIN_DIAGNOSTICO'
                    if estado_operando == 'ENCONTRADO' and dato.get('valor') is None:
                        estado_operando = 'VALOR_AUSENTE'
                    if estado_operando != 'ENCONTRADO':
                        causas.append(f'{lado.upper()}:{estado_operando}')
                causa = '|'.join(causas) or 'SIN_DETALLE_OPERANDOS'
            else:
                causa, operandos = 'SIN_DIAGNOSTICO', {}
            grupo['causas'][causa] += 1
            evidencia = {
                'fila_excel': fila.get('fila_excel'),
                'cuenta_contable': cuenta,
                'codigo_operacion': fila.get('codigo_operacion'),
                'categoria': fila.get('categoria'),
                'causa': causa, 'operandos': operandos,
            }
            pendientes_detalle.append(evidencia)
            if len(grupo['ejemplos'][causa]) < 5:
                grupo['ejemplos'][causa].append(evidencia)
    salida = {}
    for cuenta, grupo in sorted(grupos.items()):
        salida[cuenta] = {
            'filas': grupo['filas'], 'calculadas': grupo['calculadas'],
            'pendientes': grupo['pendientes'],
            'neto_parcial_no_conciliable': (
                str(grupo['neto_parcial']) if grupo['calculadas'] else None
            ),
            'causas': dict(sorted(grupo['causas'].items())),
            'ejemplos': dict(grupo['ejemplos']),
            'estado': 'PENDIENTE_OPERANDOS' if grupo['pendientes'] else 'CALCULOS_COMPLETOS_NO_HOMOLOGADOS',
            'certificado': False,
        }
    return {
        'total_filas': sum(globales.values()),
        'estados_globales': dict(globales),
        'cuentas': salida,
        'pendientes_detalle': pendientes_detalle,
        'certificado': False,
    }
