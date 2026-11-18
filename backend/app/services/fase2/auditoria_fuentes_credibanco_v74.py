"""V74: auditoria de evidencia Fase 1, por archivo y jornada (solo lectura).

No calcula correspondencias, no importa campos personales, no asigna una cuenta
contable a una etiqueta funcional y no escribe en tablas de negocio.
"""
from collections import Counter
from datetime import date

VERSION = 'V74'
INSUMOS_FUNCIONALES = (
    'HA22', 'HA26', 'HA32', 'CAET', 'CANT', 'DEPO',
    'CARTA_COMPENSACION', 'PMD', 'VSS', 'VISA_SS_INTERNATIONAL',
)
FUENTES_AUDITADAS = (
    'HA22', 'HA26', 'HA32', 'CAET', 'CANT', 'DEPO', 'CARTA_COMPENSACION',
)
TIPO_TABLA = {
    'HA22': 'con_host_resultado',
    'HA26': 'con_host_resultado',
    'HA32': 'con_host_resultado',
    'CAET': 'con_canje_detalle',
    'CANT': 'con_canje_detalle',
    'DEPO': 'con_depo_detalle',
    'CARTA_COMPENSACION': 'con_carta_compensacion_detalle',
}


def auditar_fuentes_v74(cur, id_jornada, fecha_contable):
    if isinstance(id_jornada, bool) or not isinstance(id_jornada, int) or id_jornada <= 0:
        raise ValueError('Jornada invalida en auditoria V74')
    fecha = date.fromisoformat(str(fecha_contable)).isoformat()
    # Los nombres SQL estan cerrados en la consulta; no se interpolan parametros.
    cur.execute('''
        SELECT i.tipo_insumo, i.id_archivo, i.estado AS estado_insumo,
               i.obligatorio, a.estado AS estado_archivo,
               a.proceso_origen,
               CASE WHEN i.tipo_insumo IN ('HA22','HA26','HA32')
                 THEN (SELECT COUNT(*) FROM public.con_host_resultado d WHERE d.id_archivo=i.id_archivo)
                 WHEN i.tipo_insumo IN ('CAET','CANT')
                 THEN (SELECT COUNT(*) FROM public.con_canje_detalle d WHERE d.id_archivo=i.id_archivo)
                 WHEN i.tipo_insumo = 'DEPO'
                 THEN (SELECT COUNT(*) FROM public.con_depo_detalle d WHERE d.id_archivo=i.id_archivo)
                 WHEN i.tipo_insumo = 'CARTA_COMPENSACION'
                 THEN (SELECT COUNT(*) FROM public.con_carta_compensacion_detalle d WHERE d.id_archivo=i.id_archivo)
               END AS registros_detalle,
               CASE WHEN i.tipo_insumo IN ('HA22','HA26','HA32','CAET','CANT','DEPO','CARTA_COMPENSACION')
                 THEN (SELECT COUNT(*) FROM public.con_franquicia_resultado f WHERE f.id_archivo=i.id_archivo)
               END AS registros_legado
          FROM public.con_insumo_esperado i
          LEFT JOIN public.con_archivo_carga a ON a.id_archivo=i.id_archivo
         WHERE i.id_jornada=%s
           AND i.tipo_insumo=ANY(%s)
         ORDER BY i.tipo_insumo
    ''', (id_jornada, list(FUENTES_AUDITADAS)))
    filas = cur.fetchall()
    indice = {}
    for fila in filas:
        tipo = str(fila['tipo_insumo'])
        if tipo in indice:
            raise ValueError('Insumo duplicado en jornada: ' + tipo)
        indice[tipo] = fila
    fuentes = []
    detalle_por_tipo = Counter()
    legado = 0
    for tipo in FUENTES_AUDITADAS:
        fila = indice.get(tipo)
        id_archivo = fila.get('id_archivo') if fila else None
        detalle = int(fila.get('registros_detalle') or 0) if id_archivo is not None else None
        if detalle is not None and detalle < 0:
            raise ValueError('Conteo negativo: ' + tipo)
        if detalle is not None:
            detalle_por_tipo[tipo] = detalle
            legado += int(fila.get('registros_legado') or 0)
        fuentes.append({
            'tipo_insumo': tipo,
            'id_archivo': id_archivo,
            'tabla_detalle': TIPO_TABLA[tipo],
            'estado_insumo': fila.get('estado_insumo') if fila else 'NO_REGISTRADO',
            'estado_archivo': fila.get('estado_archivo') if fila else None,
            'registros_detalle': detalle,
            'estado_evidencia': ('SIN_ARCHIVO' if id_archivo is None
                                 else 'CON_DETALLE' if detalle else 'SIN_FILAS_DETALLE'),
        })
    return {
        'version': VERSION,
        'id_jornada': id_jornada,
        'fecha_contable': fecha,
        'tipo': 'AUDITORIA_PERSISTENCIA_F1_SOLO_LECTURA',
        'insumos_funcionales_vigentes': list(INSUMOS_FUNCIONALES),
        'total_insumos_funcionales': 10,
        'fuentes_credibanco_host': fuentes,
        'total_registros_detalle_observados': sum(detalle_por_tipo.values()),
        'por_fuente': dict(detalle_por_tipo),
        'registros_resultado_contable_legado': legado,
        'requiere_llenar_con_franquicia_resultado_para_f1': False,
        'estado_transformacion': 'ORIGEN_PERSISTIDO_SIN_HOMOLOGACION',
        'cuentas_homologadas': 0,
        'certificado': False,
        'advertencia': ('Conteos estructurales por archivo, NO validacion de importes ni de procedencia bancaria. '
                        'CAET/CANT se proyectan por concepto mediante V38, no por cuenta contable aprobada. '
                        'Las filas historicas fuera del alcance funcional no participan en los contadores de esta auditoria.'),
    }
