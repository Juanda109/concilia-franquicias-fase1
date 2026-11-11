"""Evaluador contable conservador, sin Excel ni escrituras.
Solo ejecuta reglas declarativas aprobadas; jamás inventa una fuente o un cero.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

FUENTES = ('HA22', 'HA26', 'HA32')
CAMPOS = ('vl_total', 'vl_descue', 'vl_interc', 'comision_op_exitosas')


def importe(valor):
    if valor is None:
        raise ValueError('importe ausente')
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('importe invalido') from exc
    if not numero.is_finite():
        raise ValueError('importe no finito')
    return numero


def validar_regla(regla):
    necesarios = ('id_regla','cuenta','concepto','campo','fuente_host','signo','fecha_contable')
    if any(not regla.get(c) for c in necesarios):
        raise ValueError('regla incompleta')
    if regla.get('estado') != 'APROBADA':
        raise ValueError('regla no aprobada')
    if regla['campo'] not in CAMPOS or regla['fuente_host'] not in FUENTES:
        raise ValueError('campo o fuente no permitidos')
    if regla['signo'] not in (-1, 1):
        raise ValueError('signo invalido')
    if not isinstance(regla['concepto'], str):
        raise ValueError('concepto invalido')


def evaluar_regla(regla, canje, host):
    """Cruce por cuenta, concepto, fecha y una unica fuente.
    No certifica una regla si el origen o el Host carecen de evidencia.
    """
    validar_regla(regla)
    fecha = str(regla['fecha_contable'])
    origen = [r for r in canje if str(r.get('cuenta','')).strip() == regla['concepto']
              and str(r.get('fecha_contable')) == fecha]
    contrapartida = [r for r in host if str(r.get('cuenta','')).strip() == str(regla['cuenta'])
                     and r.get('tx_host') == regla['fuente_host']
                     and str(r.get('fecha_contable')) == fecha
                     and str(r.get('centro','')).strip().lstrip('0') == '17']
    resultado = {'id_regla':regla['id_regla'],'cuenta':str(regla['cuenta']),
                 'concepto':regla['concepto'],'fuente_host':regla['fuente_host'],
                 'registros_origen':len(origen),'registros_host':len(contrapartida),
                 'valor_franquicia':None,'neto_host':None,'diferencia':None,
                 'certificado':False,'estado':'PENDIENTE'}
    if not origen:
        resultado['estado']='SIN_MOVIMIENTOS_ORIGEN';return resultado
    if not contrapartida:
        resultado['estado']='SIN_HOST';return resultado
    ids_origen=[(r.get('id_archivo'),r.get('id_canje_detalle')) for r in origen]
    ids_host=[(r.get('id_archivo'),r.get('id_host_resultado')) for r in contrapartida]
    if any(None in k for k in ids_origen+ids_host) or len(set(ids_origen))!=len(ids_origen) or len(set(ids_host))!=len(ids_host):
        resultado['estado']='TRAZABILIDAD_INCOMPLETA';return resultado
    try:
        valor=sum((importe(r[regla['campo']]) for r in origen),Decimal(0))*regla['signo']
        neto=sum((importe(r['valor_debe'])-importe(r['valor_haber']) for r in contrapartida),Decimal(0))
    except (KeyError,ValueError):
        resultado['estado']='IMPORTE_INCOMPLETO';return resultado
    diferencia=valor-neto
    resultado.update(valor_franquicia=str(valor),neto_host=str(neto),
                     diferencia=str(diferencia),estado='COINCIDE_CALCULO' if diferencia==0 else 'DIFERENCIA_CALCULO',
                     ids_origen=ids_origen,ids_host=ids_host)
    return resultado


def evaluar_catalogo(reglas, canje, host):
    resultados=[]
    for regla in reglas:
        if regla.get('estado') != 'APROBADA':
            resultados.append({'id_regla':regla.get('id_regla'),'cuenta':regla.get('cuenta'),
                               'estado':'REGLA_NO_APROBADA','certificado':False})
        else:
            resultados.append(evaluar_regla(regla,canje,host))
    return {'resultados':resultados,'certificado':False,
            'nota':'Coincidencia de calculo no equivale a certificacion funcional.'}
