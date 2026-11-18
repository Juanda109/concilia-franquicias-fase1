"""Cruce verificable por cuenta literal, sin inferir homologaciones ni certificar."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

def _numero(valor):
    if valor is None: return None
    try:
        x=Decimal(str(valor))
        return x if x.is_finite() else None
    except (InvalidOperation, ValueError, TypeError): return None

def comparaciones_por_cuenta(franquicia, host):
    """Solo cuentas numéricas idénticas; las fuentes Host nunca se suman entre sí."""
    f=defaultdict(list); h=defaultdict(lambda: defaultdict(list))
    for r in franquicia:
        cuenta=str(r.get('cuenta') or '').strip()
        if cuenta.isdigit(): f[cuenta].append(r)
    for r in host:
        cuenta=str(r.get('cuenta') or '').strip()
        fuente=r.get('tx_host')
        if cuenta.isdigit() and fuente in ('HA22','HA26','HA32'):
            h[cuenta][fuente].append(r)
    salida=[]
    for cuenta in sorted(set(f)|set(h)):
        detalle=f.get(cuenta,[])
        valores=[_numero(x.get('valor')) for x in detalle]
        total_f=sum(valores,Decimal('0')) if detalle and all(v is not None for v in valores) else None
        host_por_fuente={}
        for fuente,filas in sorted(h.get(cuenta,{}).items()):
            nums=[_numero(x.get('valor_normalizado')) for x in filas]
            host_por_fuente[fuente]=str(sum(nums,Decimal('0'))) if all(v is not None for v in nums) else None
        salida.append({'cuenta':cuenta,'valor_franquicia_candidato':str(total_f) if total_f is not None else None,
                       'host_por_fuente':host_por_fuente,
                       'ids_franquicia':[x.get('id_archivo') for x in detalle],
                       'ids_host_por_fuente':{k:[x.get('id_archivo') for x in v] for k,v in h.get(cuenta,{}).items()},
                       'estado':('PENDIENTE_HOMOLOGACION' if total_f is not None and host_por_fuente else
                                 'SIN_VALOR_FRANQUICIA' if total_f is None else 'SIN_HOST'),
                       'diferencia':None,'certificado':False,
                       'nota':'Coincidencia literal de cuenta, no homologación contable; no se elige fuente ni signo.'})
    return salida
