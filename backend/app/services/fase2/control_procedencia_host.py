"""Control conservador de procedencia Host. Sin escritura a BD."""
from collections import Counter
from decimal import Decimal, InvalidOperation

BLOQUEADO = 'BLOQUEADO_SINTETICO'
NO_VERIFICADO = 'ORIGEN_NO_VERIFICADO'
VERIFICADO = 'ORIGEN_VERIFICADO'


def _texto(valor):
    return str(valor or '').upper()


def _numero(valor):
    if valor is None:
        return None
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None


def clave_correlacion(fila):
    """Correlacion diagnostica, nunca prueba de origen."""
    return (str(fila.get('empresa') or '').strip(),
            str(fila.get('nucta') or fila.get('cuenta') or '').strip(),
            str(fila.get('cedestin') or fila.get('centro') or '').strip(),
            str(fila.get('fecha_contable') or fila.get('fecont') or fila.get('fecon') or '').strip(),
            _numero(fila.get('debe') if 'debe' in fila else fila.get('valor_debe')),
            _numero(fila.get('haber') if 'haber' in fila else fila.get('valor_haber')))


def es_sintetico_explicito(fila):
    return any('PRUEBA SINTETICA' in _texto(fila.get(c)) for c in ('concepto','descon','observ','observ2'))


def evaluar_procedencia(filas, evidencias=None):
    """Evidencias: dict por id con verificado=True y origen/integridad documentados.

    El campo verificado no se infiere del archivo; debe venir de un proceso
    de validacion independiente. Nunca se habilita con solo un texto libre.
    """
    evidencias = evidencias or {}
    marcadas = {clave_correlacion(f) for f in filas if es_sintetico_explicito(f)}
    resultados = []
    for fila in filas:
        identificador = fila.get('id_host_resultado', fila.get('id_detalle'))
        tipo = str(fila.get('tx_host') or fila.get('tx_origen') or '').upper()
        explicito = es_sintetico_explicito(fila)
        correlacion = tipo == 'HA32' and clave_correlacion(fila) in marcadas
        evidencia = evidencias.get(identificador, {})
        if explicito:
            estado, motivo = BLOQUEADO, 'MARCADOR_SINTETICO_EXPLICITO'
        elif correlacion:
            estado, motivo = NO_VERIFICADO, 'CORRELACION_CON_SINTETICO'
        elif (evidencia.get('verificado') is True and evidencia.get('origen')
              and evidencia.get('integridad_verificada') is True):
            estado, motivo = VERIFICADO, 'EVIDENCIA_EXTERNA_VALIDADA'
        else:
            estado, motivo = NO_VERIFICADO, 'EVIDENCIA_INSUFICIENTE'
        resultados.append({'id_registro': identificador, 'fuente': tipo,
                           'estado': estado, 'motivo': motivo,
                           'certificable_por_procedencia': estado == VERIFICADO})
    return {'conteos': dict(Counter(r['estado'] for r in resultados)),
            'registros': resultados,
            'advertencia': 'Origen verificado no equivale a conciliacion certificada; requiere matriz aprobada.'}
