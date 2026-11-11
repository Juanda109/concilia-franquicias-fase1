"""INC51: exposicion diagnostica de TOTALES CAET/CANT; no homologacion."""
from app.services.fase2.reporte_host_inc50 import consultar as consultar_inc50
from app.services.fase2.integracion_depo_inc56i import consultar_depo_jornada

# Homologacion de cuenta aprobada; NO implica formula, signo ni conciliacion.
CUENTAS_HOMOLOGADAS = {
    '017-CANJE RECIBIDO TARJETA CREDITO': '299095302',
    '017-CANJE RECIBIDO TARJETA CREDITO REVERSION VENTAS 26 VLR. TOTAL': '299095302',
}

def enriquecer(reporte):
    if reporte.get('certificado') is not False:
        raise ValueError('Se requiere reporte no certificado')
    totales = reporte.get('totales_diagnosticos') or []
    conocidos = {str(d.get('concepto')) for d in reporte.get('detalle', [])}
    sin_correspondencia = []
    for t in totales:
        if str(t.get('A')) not in conocidos:
            sin_correspondencia.append({
                'concepto_origen': t.get('A'), 'cantidad': t.get('B'),
                'vl_interc': t.get('C'), 'vl_total': t.get('D'),
                'archivos_origen': list(t.get('archivos') or []),
                'lineas_origen': list(t.get('lineas_origen') or []),
                'estado': 'CUENTA_HOMOLOGADA_FORMULA_PENDIENTE' if str(t.get('A')) in CUENTAS_HOMOLOGADAS else 'SIN_CORRESPONDENCIA_LITERAL_NO_HOMOLOGADO',
                'cuenta': CUENTAS_HOMOLOGADAS.get(str(t.get('A'))),
                'cuenta_homologada': CUENTAS_HOMOLOGADAS.get(str(t.get('A'))),
                'homologacion_cuenta': str(t.get('A')) in CUENTAS_HOMOLOGADAS})
    respuesta = dict(reporte)
    respuesta['diagnostico_credibanco_inc51'] = {
        'fuentes': ['CAET','CANT'], 'estado':'NO_HOMOLOGADO',
        'columnas_adicionales': ['cantidad_operaciones','vl_interc','vl_total'],
        'agregados_sin_correspondencia': sin_correspondencia,
        'depo': {'estado':'PENDIENTE_REGLAS_FASE_2',
                 'advertencia':'DEPO no se suma a CAET/CANT ni se proyecta a cuentas.'},
        'advertencia':'Los agregados sin correspondencia no alimentan Valor Franquicia.'}
    respuesta['certificado'] = False
    return respuesta

def consultar(jornada, fuente_host=None):
    respuesta = enriquecer(consultar_inc50(jornada))
    respuesta['diagnostico_credibanco_inc51']['depo'] = consultar_depo_jornada(jornada, fuente_host=fuente_host)
    return respuesta
