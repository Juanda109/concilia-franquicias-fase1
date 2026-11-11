"""Diagnostico de las 13 cuentas Credibanco en el Reporte Maestro ORIGINAL.

La fecha/cuenta/Host no acreditan homologacion monetaria ni origen bancario.
No cruza ni suma fuentes HA22/HA26/HA32; no escribe en base de datos.
"""
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation

from app.services.fase2.clasificacion_franquicias_v39 import CUENTAS_POR_FRANQUICIA

VERSION = 'V72'
CUENTAS = tuple(CUENTAS_POR_FRANQUICIA['CREDIBANCO'])
FUENTES = ('HA22', 'HA26', 'HA32')
ESTADOS = frozenset(('PENDIENTE_HOMOLOGACION', 'SIN_MOVIMIENTOS_HOST',
                     'HOST_INCOMPLETO', 'FUERA_CATALOGO_HOST'))


def _entero_no_negativo(valor, descripcion):
    if isinstance(valor, bool):
        raise ValueError('Valor booleano no permitido: ' + descripcion)
    try:
        n = int(valor)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Cantidad invalida: ' + descripcion) from exc
    if n < 0 or str(valor).strip() not in (str(n), str(n) + '.0'):
        raise ValueError('Cantidad invalida: ' + descripcion)
    return n


def _validar_neto_si_existe(mov, clave):
    # Validacion estructural; NO significa que el movimiento sea bancario.
    if mov.get('neto') is None:
        return
    try:
        n = Decimal(str(mov['neto']))
        if not n.is_finite():
            raise ValueError('Neto no finito: ' + clave)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('Neto Host invalido: ' + clave) from exc


def construir_estado_v72(id_jornada, fecha_contable, cobertura_host,
                         cruces_v36, movimientos_host):
    """Transforma evidencia existente del reporte en estados, sin homologar.

    Rechaza cobertura incompleta o contradictoria. Incluso si V36 dispone de
    calculos, aqui permanecen NO certificados por no existir prueba bancaria.
    """
    if isinstance(id_jornada, bool) or not isinstance(id_jornada, int) or id_jornada <= 0:
        raise ValueError('ID jornada invalido')
    try:
        fecha = date.fromisoformat(str(fecha_contable))
    except ValueError as exc:
        raise ValueError('Fecha jornada invalida') from exc
    if not isinstance(cobertura_host, list) or len(cobertura_host) != 29:
        raise ValueError('Se esperan 29 cuentas Host con evidencia estructural')
    if not isinstance(cruces_v36, dict) or cruces_v36.get('certificado') is not False:
        raise ValueError('Estado V36 sin confirmacion de no certificacion')
    if not isinstance(movimientos_host, list):
        raise ValueError('Movimientos Host invalidos')
    indice = {}
    for c in cobertura_host:
        cuenta = str(c.get('cuenta') or '').strip()
        if not cuenta.isdigit() or cuenta in indice:
            raise ValueError('Cuenta Host invalida o duplicada: ' + cuenta)
        indice[cuenta] = c
    if len(indice) != 29:
        raise ValueError('Catalogo Host inconsistente')

    fuera = Counter()
    for h in movimientos_host:
        cuenta = str(h.get('cuenta') or '').strip()
        fuente = str(h.get('tx_host') or '').strip().upper()
        centro = str(h.get('centro') or '').strip()
        if cuenta in CUENTAS and cuenta not in indice and fuente in FUENTES and centro in ('', '17', '0017'):
            fuera[cuenta] += 1

    calculos = {}
    if cruces_v36.get('estado') == 'CALCULO_NO_CERTIFICADO':
        for x in cruces_v36.get('resultados') or []:
            cuenta = str(x.get('cuenta') or '').strip()
            if cuenta in CUENTAS:
                calculos.setdefault(cuenta, []).append({
                    'id_regla': str(x.get('id_regla') or ''),
                    'estado': str(x.get('estado') or ''),
                    'fuente_host': str(x.get('fuente_host') or ''),
                    'certificado': False,
                })

    filas = []
    for cuenta in CUENTAS:
        c = indice.get(cuenta)
        motivos = ['NO_HAY_CORRESPONDENCIA_MONETARIA_ACREDITADA',
                   'ORIGEN_BANCARIO_HOST_NO_ACREDITADO']
        host_por_fuente = {}
        if c is None:
            estado = 'FUERA_CATALOGO_HOST'
            motivos.insert(0, 'CUENTA_FUERA_CATALOGO_HOST_29')
            movimientos = fuera[cuenta]
            if movimientos:
                motivos.append('HOST_OBSERVADO_FUERA_CATALOGO_NO_HOMOLOGADO')
            franquicia_documental = None
        else:
            movimientos = 0
            for fuente in FUENTES:
                m = (c.get('monetario_host') or {}).get(fuente) or {}
                cantidad = _entero_no_negativo(m.get('cantidad', 0), cuenta + ' ' + fuente)
                _validar_neto_si_existe(m, cuenta + ' ' + fuente)
                estado_fuente = str(m.get('estado') or 'SIN_MOVIMIENTOS')
                if estado_fuente not in ('CON_MOVIMIENTOS', 'SIN_MOVIMIENTOS', 'DATO_INCOMPLETO'):
                    raise ValueError('Estado Host no reconocido: ' + estado_fuente)
                if cantidad == 0 and estado_fuente != 'SIN_MOVIMIENTOS':
                    raise ValueError('Estado Host inconsistente sin movimientos')
                if cantidad and estado_fuente == 'SIN_MOVIMIENTOS':
                    raise ValueError('Estado Host inconsistente con movimientos')
                movimientos += cantidad
                host_por_fuente[fuente] = {'cantidad': cantidad, 'estado': estado_fuente}
            if any(m['estado'] == 'DATO_INCOMPLETO' for m in host_por_fuente.values()):
                estado = 'HOST_INCOMPLETO'
                motivos.append('DEBE_HABER_O_NETO_HOST_INCOMPLETO')
            elif not movimientos:
                estado = 'SIN_MOVIMIENTOS_HOST'
                motivos.append('SIN_MOVIMIENTOS_HOST_EN_CATALOGO')
            else:
                estado = 'PENDIENTE_HOMOLOGACION'
            franquicia_documental = c.get('franquicia_relacionada')
            if franquicia_documental and 'CREDIBANCO' not in [
                    s.strip().upper() for s in str(franquicia_documental).split('|')]:
                motivos.append('FRANQUICIA_DOCUMENTAL_DIFIERE_DE_CATALOGO_PANTALLA')
        if calculos.get(cuenta):
            motivos.append('CALCULO_V36_NO_CERTIFICA_CUADRE')
        filas.append({
            'cuenta': cuenta,
            'franquicia': 'CREDIBANCO',
            'estado': estado,
            'motivos': motivos,
            'movimientos_host_observados': movimientos,
            'movimientos_por_fuente': host_por_fuente,
            'franquicia_documental': franquicia_documental,
            'calculos_v36_no_certificados': calculos.get(cuenta, []),
            'correspondencia_aprobada': False,
            'procedencia_host_acreditada': False,
            'valor_franquicia_homologado': None,
            'diferencia_homologada': None,
            'certificado': False,
        })
    cuentas_unicas = {r['cuenta'] for r in filas}
    if len(cuentas_unicas) != 13:
        raise ValueError('Catalogo Credibanco invalido')
    conteo = Counter(r['estado'] for r in filas)
    return {
        'version': VERSION,
        'tipo': 'DIAGNOSTICO_REAL_SOLO_LECTURA',
        'id_jornada': id_jornada,
        'fecha_contable': fecha.isoformat(),
        'franquicia': 'CREDIBANCO',
        'cuentas': filas,
        'indicadores': {
            'cuentas_credibanco': len(filas),
            'pendiente_homologacion': conteo['PENDIENTE_HOMOLOGACION'],
            'sin_movimientos_host': conteo['SIN_MOVIMIENTOS_HOST'],
            'host_incompleto': conteo['HOST_INCOMPLETO'],
            'fuera_catalogo_host': conteo['FUERA_CATALOGO_HOST'],
            'cruces_homologados': 0,
            'conciliados': 0,
            'diferencias_homologadas': 0,
            'incorporados_maestro': 0,
        },
        'reglas_v36_estado': str(cruces_v36.get('estado') or 'SIN_REGLAS_APROBADAS'),
        'certificado': False,
        'aviso': ('Diagnostico por cuenta. HA22/HA26/HA32 son fuentes independientes, '
                  'no un total sumable. Sin origen Host bancario acreditado ni '
                  'correspondencias monetarias aprobadas: no hay diferencia calculable.'),
    }
