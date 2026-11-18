"""Inc39: contrato inmutable para la tabla aprobada de 11 columnas."""
COLUMNAS=('franquicia','cuenta','concepto','valor_franquicia','ha22','ha26','ha32',
         'total_host','diferencia','estado_conciliacion','accion')
FRANQUICIAS=frozenset({'CREDIBANCO','REDEBAN','VISA'})
def validar_fila(fila):
    if set(fila)!=set(COLUMNAS): raise ValueError('Columnas del Reporte Maestro incompletas o adicionales')
    if fila['franquicia'] not in FRANQUICIAS: raise ValueError('Franquicia no autorizada')
    if fila['estado_conciliacion'] not in ('PENDIENTE_F2','PENDIENTE_HOMOLOGACION','CALCULADO_NO_HOMOLOGADO','SIN_INFORMACION'):
        raise ValueError('Estado no certificado obligatorio')
    if fila['total_host'] is not None or fila['diferencia'] is not None:
        raise ValueError('No se autorizan totales ni diferencias sin correspondencias homologadas')
    return True
def contrato_vacio():
    return {'columnas':list(COLUMNAS),'filas':[],
      'indicadores':{'cruces':0,'conciliados':0,'diferencias':0,'incorporados_maestro':0},
      'certificado':False,'origen':'DIAGNOSTICO_INC39'}
