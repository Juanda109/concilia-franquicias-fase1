"""Motor de evaluacion no certificada. Solo compara si la regla esta explicitamente completa.
No presupone que la fuente Host o el signo sean homologados.
"""
from decimal import Decimal, InvalidOperation
from collections import defaultdict

FUENTES = {'HA22','HA26','HA32'}

def importe(x):
    if x is None: raise ValueError('Importe ausente')
    try:
        v=Decimal(str(x))
    except (InvalidOperation,ValueError) as exc:
        raise ValueError('Importe invalido') from exc
    if not v.is_finite(): raise ValueError('Importe no finito')
    return v

def evaluar(cuenta, registros_canje, registros_host, regla=None):
    """Regla: fuente_host, signo (+1/-1), campo, fecha_host, centro, familia.
    Solo resultados de prueba, incluso con regla completa. El uso certificado requiere aprobacion externa.
    """
    resultado={'cuenta':str(cuenta),'certificado':False,'diferencia':None,
               'valor_franquicia':None,'neto_host':None,'estado':None,
               'ids_canje':sorted({str(r['id_canje_detalle']) for r in registros_canje}),
               'ids_host':sorted({str(r['id_host_resultado']) for r in registros_host})}
    if not registros_canje:
        resultado['estado']='SIN_CONCEPTO';return resultado
    if not registros_host:
        resultado['estado']='SIN_HOST';return resultado
    fuentes={str(h.get('tx_host') or '').upper() for h in registros_host}
    if not regla:
        resultado['estado']='PENDIENTE_REGLA_MONETARIA';return resultado
    obligatorios=('fuente_host','signo','campo','fecha_host','centro','familia')
    if any(regla.get(k) in (None,'') for k in obligatorios):
        resultado['estado']='REGLA_INCOMPLETA';return resultado
    if regla['fuente_host'] not in FUENTES or regla['signo'] not in (-1,1):
        resultado['estado']='REGLA_INVALIDA';return resultado
    if regla['fuente_host'] not in fuentes:
        resultado['estado']='SIN_FUENTE_HOST_REQUERIDA';return resultado
    # Filtrar por cuenta, centro, fuente y fecha exactos; nunca sumar HA22/HA26/HA32.
    host=[h for h in registros_host if str(h.get('cuenta'))==str(cuenta)
          and str(h.get('tx_host')).upper()==regla['fuente_host']
          and str(h.get('centro')).zfill(4)==str(regla['centro']).zfill(4)
          and str(h.get('fecha_contable'))==str(regla['fecha_host'])]
    if not host:
        resultado['estado']='SIN_HOST_EN_VENTANA';return resultado
    # Deduplicar por identificador fisico; rechazo si el mismo registro se intenta sumar dos veces.
    if len({h['id_host_resultado'] for h in host})!=len(host):
        resultado['estado']='HOST_DUPLICADO';return resultado
    canje=[r for r in registros_canje if r.get('familia')==regla['familia']]
    if not canje:
        resultado['estado']='SIN_FAMILIA';return resultado
    if len({r['id_canje_detalle'] for r in canje})!=len(canje):
        resultado['estado']='CANJE_DUPLICADO';return resultado
    try:
        externo=sum((importe(r.get(regla['campo'])) for r in canje),Decimal('0'))*regla['signo']
        neto=sum((importe(h.get('valor_debe'))-importe(h.get('valor_haber')) for h in host),Decimal('0'))
    except ValueError:
        resultado['estado']='IMPORTE_INCOMPLETO';return resultado
    dif=externo-neto
    resultado.update({'valor_franquicia':str(externo),'neto_host':str(neto),'diferencia':str(dif),
        'estado':'COINCIDE_PRUEBA' if dif==0 else 'DIFERENCIA_PRUEBA',
        'fuente_host':regla['fuente_host'],'fecha_host':str(regla['fecha_host']),
        'ids_canje':sorted(str(r['id_canje_detalle']) for r in canje),
        'ids_host':sorted(str(h['id_host_resultado']) for h in host)})
    return resultado
