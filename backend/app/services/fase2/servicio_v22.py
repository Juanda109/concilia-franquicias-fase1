"""Ensayo aislado; nunca consulta BD ni certifica conciliaciones."""
from decimal import Decimal

def obtener_ensayo():
    casos = [
      ('299095301','CANJE RECIBIDO TARJETA DEBITO','vl_total','10000.00','10000.00'),
      ('299095300','COMISIONES EXIT. TARJETA DEBITO ONLINE','comision_op_exitosas','7450.00','7400.00'),
      ('299095880','CANJE RECIBIDO TARJETA DEBITO REGALO',None,None,None),
    ]
    filas=[]
    for cuenta,concepto,campo,externo,host in casos:
        dif = str((Decimal(externo)-Decimal(host)).quantize(Decimal('0.01'))) if host else None
        filas.append(dict(cuenta=cuenta,concepto=concepto,campo_monetario=campo,
          valor_franquicia=externo,neto_host=host,diferencia=dif,
          estado='SIN_HOST_ENSAYO' if host is None else 'COINCIDE_ENSAYO' if dif=='0.00' else 'DIFERENCIA_ENSAYO',
          certificado=False,fuente_host_supuesta='HA22' if host else None))
    return dict(modo='ENSAYO_SINTETICO_AISLADO',certificado=False,origen='MEMORIA_NO_POSTGRESQL',
      jornada_real_asociada=None,advertencia='Importes, fuente Host y fecha son supuestos NO APROBADOS de ensayo.',resultados=filas)
