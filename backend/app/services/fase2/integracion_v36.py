"""Cruces calculados con V35 y reglas explicitamente aprobadas. No certifica."""
from app.services.fase2.motor_monetario_v35 import evaluar_catalogo

def construir_cruces_v36(cur, jornada, reglas):
    if not isinstance(reglas, list):
        raise ValueError('catalogo de reglas invalido')
    aprobadas = [r for r in reglas if r.get('estado') == 'APROBADA']
    if not aprobadas:
        return {'resultados': [], 'certificado': False, 'estado': 'SIN_REGLAS_APROBADAS', 'nota': 'No se inventan correspondencias ni importes.'}
    cur.execute('''SELECT d.id_canje_detalle,d.id_archivo,d.cuenta,d.fecha_contable,
                          d.vl_total,d.vl_descue,d.vl_interc,d.comision_op_exitosas
                   FROM public.con_canje_detalle d
                   WHERE EXISTS (SELECT 1 FROM public.con_insumo_esperado i
                                 WHERE i.id_jornada=%s AND i.id_archivo=d.id_archivo)
                   ORDER BY d.id_canje_detalle''', (jornada,))
    cols=[c.name for c in cur.description]
    canje=[dict(zip(cols, r)) for r in cur.fetchall()]
    cur.execute('''SELECT h.id_host_resultado,h.id_archivo,h.cuenta,h.centro,h.tx_host,
                          h.fecha_contable,h.valor_debe,h.valor_haber
                   FROM public.con_host_resultado h
                   WHERE EXISTS (SELECT 1 FROM public.con_insumo_esperado i
                                 WHERE i.id_jornada=%s AND i.id_archivo=h.id_archivo)
                   ORDER BY h.id_host_resultado''', (jornada,))
    cols=[c.name for c in cur.description]
    host=[dict(zip(cols, r)) for r in cur.fetchall()]
    result=evaluar_catalogo(reglas,canje,host)
    result['estado']='CALCULO_NO_CERTIFICADO'
    return result
