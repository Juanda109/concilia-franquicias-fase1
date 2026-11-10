"""Motor puro F2: correspondencias aprobadas, sin acceso a BD ni escrituras."""
from decimal import Decimal, InvalidOperation
from pathlib import Path
import json

HOST_FIELDS = {'valor_debe', 'valor_haber', 'valor_normalizado', 'valor_saldo'}
FRAN_FIELDS = {'vl_total', 'vl_interc', 'comision_op_exitosas', 'tii_recibida_emisor_visa_op_rever_ventas'}
SOURCES = {'HA22', 'HA26', 'HA32'}


def decimal_required(value, field):
    if value is None or isinstance(value, bool) or str(value).strip() == '':
        raise ValueError(f'{field}: importe ausente')
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'{field}: importe invalido') from exc
    if not n.is_finite():
        raise ValueError(f'{field}: importe no finito')
    return n


def load_rules(path):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if data.get('fase') != 2 or not isinstance(data.get('reglas'), list):
        raise ValueError('Matriz F2 invalida')
    ids = set()
    rules = []
    for rule in data['reglas']:
        rid = rule['id_regla']
        if not isinstance(rid, str) or not rid.strip() or rid in ids:
            raise ValueError('Identificador de regla invalido o duplicado')
        ids.add(rid)
        if rule['estado_regla'] not in ('PROPUESTA', 'APROBADA', 'INACTIVA'):
            raise ValueError('Estado de regla invalido')
        if rule['fuente_host'] not in SOURCES or rule['tipo_insumo'] not in ('CAET', 'CANT'):
            raise ValueError('Fuente no permitida')
        if rule['campo_host'] not in HOST_FIELDS or rule['campo_franquicia'] not in FRAN_FIELDS:
            raise ValueError('Campo no permitido')
        factor = decimal_required(rule['factor_signo'], 'factor_signo')
        tolerance = decimal_required(rule['tolerancia'], 'tolerancia')
        if factor not in (Decimal('1'), Decimal('-1')) or tolerance < 0:
            raise ValueError('Factor o tolerancia invalidos')
        for name in ('cuenta_host', 'cuenta_franquicia'):
            if not isinstance(rule.get(name), str) or not rule[name].strip():
                raise ValueError(f'{name} requerido')
        rules.append(rule)
    return rules


def synthetic(host):
    # Conservador: etiquetas de prueba y bandera explicita; HA32 sin concepto no se certifica por ausencia de etiqueta.
    concept = str(host.get('concepto') or '').upper()
    return bool(host.get('es_sintetico') is True or 'SINTETIC' in concept or 'PRUEBA' in concept)


def matches(rule, host, fran):
    checks = (('fuente_host', 'tx_host'), ('cuenta_host', 'cuenta'), ('centro_host', 'centro'), ('concepto_host', 'concepto'))
    for rk, hk in checks:
        if rule.get(rk) not in (None, '') and str(rule[rk]) != str(host.get(hk)):
            return False
    if rule['tipo_insumo'] != fran.get('tipo_archivo'):
        return False
    if rule['cuenta_franquicia'] != fran.get('cuenta'):
        return False
    if rule.get('fecha_contable') and str(rule['fecha_contable']) != str(host.get('fecha_contable')):
        return False
    if str(host.get('fecha_contable')) != str(fran.get('fecha_contable')):
        return False
    return True


def evaluate(host, fran, rules):
    """Evalua un par previamente seleccionado; no empareja filas ni suma fuentes Host."""
    base = {'id_host': host.get('id_host_resultado'), 'id_franquicia': fran.get('id_canje_detalle'),
            'id_archivo_host': host.get('id_archivo'), 'id_archivo_franquicia': fran.get('id_archivo')}
    if synthetic(host):
        return {**base, 'estado': 'BLOQUEADO_SINTETICO', 'id_regla': None}
    if host.get('origen_verificado') is not True:
        return {**base, 'estado': 'ORIGEN_NO_VERIFICADO', 'id_regla': None}
    approved = [r for r in rules if r['estado_regla'] == 'APROBADA' and matches(r, host, fran)]
    if not approved:
        return {**base, 'estado': 'SIN_MAPEO', 'id_regla': None}
    if len(approved) > 1:
        return {**base, 'estado': 'MAPEO_AMBIGUO', 'id_regla': None,
                'reglas': sorted(r['id_regla'] for r in approved)}
    rule = approved[0]
    try:
        host_val = decimal_required(host.get(rule['campo_host']), rule['campo_host'])
        fran_val = decimal_required(fran.get(rule['campo_franquicia']), rule['campo_franquicia'])
        factor = decimal_required(rule['factor_signo'], 'factor_signo')
        tolerance = decimal_required(rule['tolerancia'], 'tolerancia')
    except ValueError as exc:
        return {**base, 'estado': 'DATOS_INSUFICIENTES', 'id_regla': rule['id_regla'], 'motivo': str(exc)}
    normalized = host_val * factor
    delta = normalized - fran_val
    return {**base, 'estado': 'COINCIDE' if abs(delta) <= tolerance else 'DIFERENCIA',
            'id_regla': rule['id_regla'], 'host_normalizado': str(normalized),
            'franquicia_valor': str(fran_val), 'diferencia': str(delta), 'tolerancia': str(tolerance)}
