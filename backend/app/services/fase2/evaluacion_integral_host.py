"""F2-25: evaluación conservadora de firma, vigencia y procedencia Host.

Nunca eleva procedencia ni certifica conciliaciones; requiere insumos de confianza externos.
"""
from __future__ import annotations
from collections import Counter
from pathlib import Path
from app.services.fase2.integracion_firmas_host import integrar_firmas
from app.services.fase2.vigencia_revocacion_host import verificar_vigencia_revocacion


def evaluar_integral(filas, archivos, evidencias, atestaciones, controles, *,
                     claves_confiables=None, autorizaciones_externas=None,
                     claves_revocadas=None, autorizaciones_revocadas=None,
                     claves_autoridad=None, ahora=None):
    """Devuelve diagnóstico anotado; jamás altera estados ni base de datos.

    controles: id_archivo -> control de vigencia/revocación firmado independientemente.
    Los mapas de confianza deben proceder de una configuración externa aprobada.
    """
    ids = {r['id_archivo'] for r in filas}
    if set(controles) - ids:
        raise ValueError('CONTROL_FUERA_DE_POBLACION')
    base = integrar_firmas(
        filas, archivos, evidencias, atestaciones,
        claves_confiables=claves_confiables,
        autorizaciones_externas=autorizaciones_externas,
        claves_revocadas=claves_revocadas,
        autorizaciones_revocadas=autorizaciones_revocadas,
    )
    decisiones = {}
    for id_archivo in sorted(ids):
        if id_archivo not in controles or id_archivo not in atestaciones:
            decision = {'estado': 'ORIGEN_NO_VERIFICADO', 'motivos': ['CONTROL_VIGENCIA_AUSENTE']}
        else:
            decision = verificar_vigencia_revocacion(
                atestaciones[id_archivo], controles[id_archivo],
                claves_autoridad=claves_autoridad, ahora=ahora,
            )
        decisiones[id_archivo] = decision
    for registro in base['registros']:
        decision = decisiones[registro['id_archivo']]
        registro['estado_vigencia'] = decision['estado']
        registro['motivos_vigencia'] = decision['motivos']
        firma_ok = registro['estado_firma'] == 'EVIDENCIA_EXTERNA_VERIFICADA'
        vigencia_ok = decision['estado'] == 'CONTROL_VIGENCIA_VALIDADO'
        registro['evidencia_integral_validada'] = bool(firma_ok and vigencia_ok)
        # La procedencia anterior siempre prevalece, incluso si las evidencias son válidas.
        registro['certificable'] = False
    base['conteos_vigencia'] = dict(Counter(r['estado_vigencia'] for r in base['registros']))
    base['conteos_evidencia_integral'] = dict(Counter(str(r['evidencia_integral_validada']) for r in base['registros']))
    base['cruces_certificados'] = 0
    base.setdefault('advertencias', []).append('Evidencia integral no constituye aprobación contable')
    return base
