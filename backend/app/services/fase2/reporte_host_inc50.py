"""Diagnostico Host para Reporte Maestro, sin homologacion contable."""
from collections import defaultdict

FUENTES = ('HA22','HA26','HA32')

def integrar_host(reporte: dict, diagnostico: dict) -> dict:
    if reporte.get('certificado') is not False or diagnostico.get('certificado') is not False:
        raise ValueError('Solo se permiten respuestas diagnosticas no certificadas')
    if int(reporte['id_jornada']) != int(diagnostico['id_jornada']):
        raise ValueError('Jornadas diferentes')
    if len(reporte.get('columnas', [])) != 11:
        raise ValueError('Contrato de 11 columnas no valido')
    grupos=defaultdict(list)
    for fila in diagnostico.get('filas', []):
        if fila.get('fuente') not in FUENTES: continue
        cuenta=str(fila.get('cuenta') or '')
        if cuenta: grupos[cuenta].append(dict(fila))
    detalles=[]
    for detalle in reporte.get('detalle', []):
        d=dict(detalle)
        registros=grupos.get(str(d.get('cuenta') or ''), [])
        d['host_diagnostico_inc50']={
            'estado':'DIAGNOSTICO_NO_HOMOLOGADO',
            'datos_sinteticos_o_no_verificados':True,
            'fuentes':{fuente:[r for r in registros if r['fuente']==fuente] for fuente in FUENTES},
            'total_host_homologado':None,'diferencia_homologada':None,
            'advertencia':'Importes por fuente solo para diagnostico; no sumar HA22, HA26 y HA32.'}
        detalles.append(d)
    resultado=dict(reporte)
    resultado['detalle']=detalles
    resultado['diagnostico_host_inc50']={
        'estado':'NO_HOMOLOGADO', 'certificado':False,
        'agrupaciones':diagnostico.get('filas', []),
        'advertencia':'Host sin correspondencia contable certificada.'}
    resultado['certificado']=False
    return resultado

def consultar(jornada: int):
    from app.services.fase2.reporte_api_credibanco_inc47 import consultar as consultar_credibanco
    from app.services.fase2.diagnostico_host_inc49 import obtener_diagnostico_host
    return integrar_host(consultar_credibanco(jornada), obtener_diagnostico_host(jornada))
