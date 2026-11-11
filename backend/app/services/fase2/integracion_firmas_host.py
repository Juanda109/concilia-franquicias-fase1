"""F2-23: anexa verificacion criptografica a diagnosticos sin elevar certificacion."""
from __future__ import annotations
from collections import Counter
from pathlib import Path
from app.services.fase2.integracion_evidencias_host import integrar
from app.services.fase2.acreditacion_firmada_host import verificar_atestacion


def integrar_firmas(filas, archivos, evidencias, atestaciones, *, claves_confiables=None,
                    autorizaciones_externas=None, claves_revocadas=None,
                    autorizaciones_revocadas=None):
    """Entradas confiables suministradas por integrador externo, nunca por atestacion.

    Sin fuente de revocacion confiable/actualizada no se puede aprobar autenticidad.
    """
    base = integrar(filas, archivos, evidencias)
    ids = {r['id_archivo'] for r in filas}
    if set(atestaciones) - ids:
        raise ValueError('ATESTACION_FUERA_DE_POBLACION')
    decisiones = {}
    for archivo_id in sorted(ids):
        ruta = archivos.get(archivo_id)
        if ruta is None:
            decision = {'estado': 'ORIGEN_NO_VERIFICADO', 'motivos': ['ARCHIVO_ORIGINAL_NO_DISPONIBLE'], 'certificable': False}
        elif claves_revocadas is None or autorizaciones_revocadas is None:
            decision = {'estado': 'ORIGEN_NO_VERIFICADO', 'motivos': ['REVOCACION_NO_VERIFICABLE'], 'certificable': False}
        else:
            att = atestaciones.get(archivo_id)
            datos = att.get('datos', {}) if isinstance(att, dict) else {}
            if datos.get('emisor') in claves_revocadas or datos.get('id_autorizacion') in autorizaciones_revocadas:
                decision = {'estado': 'ORIGEN_NO_VERIFICADO', 'motivos': ['CREDENCIAL_REVOCADA'], 'certificable': False}
            else:
                decision = verificar_atestacion(Path(ruta), att, claves_confiables, autorizaciones_externas)
                if decision['estado'] == 'EVIDENCIA_EXTERNA_VERIFICADA' and datos.get('id_archivo') != archivo_id:
                    decision = {'estado': 'ORIGEN_NO_VERIFICADO', 'motivos': ['ID_ARCHIVO_NO_COINCIDE'], 'certificable': False}
        decisiones[archivo_id] = decision
    for r in base['registros']:
        d = decisiones[r['id_archivo']]
        r['estado_firma'] = d['estado']
        r['motivos_firma'] = d['motivos']
        r['certificable'] = False
    base['conteos_firma'] = dict(Counter(r['estado_firma'] for r in base['registros']))
    base['cruces_certificados'] = 0
    base['advertencias'].append('Acreditacion firmada no habilita reglas contables ni certificacion')
    return base


def diagnosticar_jornada_1377_firmada():
    """Sin integracion externa aprobada, se mantiene diagnostico anterior sin elevaciones."""
    from app.services.fase2.integracion_evidencias_host import diagnosticar_jornada_1377
    base = diagnosticar_jornada_1377()
    for r in base['registros']:
        r['estado_firma'] = 'ORIGEN_NO_VERIFICADO'
        r['motivos_firma'] = ['SIN_ANCLA_DE_CONFIANZA']
        r['certificable'] = False
    base['conteos_firma'] = {'ORIGEN_NO_VERIFICADO': len(base['registros'])}
    base['cruces_certificados'] = 0
    return base
