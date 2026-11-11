# CONCILIA_EXCLUSION_MEP_V2
"""Consulta diagnostica de resultados por jornada. Nunca concilia ni certifica."""
from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row
from app.repositories.database import connection
from app.services.fase2.cobertura_29_cuentas import construir_cobertura_cuentas


router = APIRouter(prefix='/api/v1/jornadas', tags=['Reporte Maestro diagnostico'])

INSUMOS = ('HA22','HA26','HA32','CAET','CANT','DEPO','CARTA_COMPENSACION','PMD','VSS')


def armar_reporte(jornada, archivos, franquicia, host):
    id_jornada, fecha, estado = jornada
    entradas = {tipo: [] for tipo in INSUMOS}
    for a in archivos:
        if a['tipo_archivo'] in entradas:
            entradas[a['tipo_archivo']].append(a)
    def fila(r, fuente):
        return {'fuente': fuente, 'id_archivo': r['id_archivo'],
                'cuenta': r.get('cuenta'), 'concepto': r.get('concepto'),
                'valor': str(r['valor']) if r.get('valor') is not None else None,
                'estado': 'PROCESADO_NO_CONCILIADO', 'certificado': False,
                'correlation_id': r['correlation_id']}
    return {
        'id_jornada': id_jornada, 'fecha_contable': str(fecha), 'estado_jornada': estado,
        'origen': 'POSTGRESQL_DIAGNOSTICO', 'certificado': False,
        'cruces': [], 'indicadores': {'cruces': 0, 'conciliados': 0, 'diferencias': 0, 'incorporados_maestro': 0},
        'insumos': [{'tipo_insumo': t, 'archivos': len(entradas[t]),
                     'valor_mostrado': '0', 'valor_provisional': True,
                     'estado': 'PENDIENTE_REGLAS_F2'} for t in INSUMOS if t not in ('HA22','HA26','HA32','CAET','CANT')],
        'resultados_franquicia': [fila(r, r['franquicia']) for r in franquicia],
        'resultados_host': [{**fila(r, r['tx_host']), 'valor': str(r['valor_normalizado'])} for r in host],
        'advertencias': ['Cero provisional no equivale a cero calculado.',
                         'No existen correspondencias contables homologadas para generar cruces.',
                         'La jornada y los resultados no acreditan certificacion.']
    }


@router.get('/{id_jornada}/reporte-maestro-diagnostico')
def reporte_maestro_diagnostico(id_jornada: int):
    if id_jornada <= 0:
        raise HTTPException(status_code=422, detail='Jornada invalida')
    try:
        with connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute('SET TRANSACTION READ ONLY')
                cur.execute('SELECT id_jornada, fecha_contable, estado FROM public.con_jornada WHERE id_jornada=%s', (id_jornada,))
                j = cur.fetchone()
                if j is None:
                    raise HTTPException(status_code=404, detail='Jornada no encontrada')
                cur.execute('''SELECT DISTINCT a.id_archivo, a.tipo_archivo, a.fecha_contable, a.estado
                               FROM public.con_insumo_esperado i JOIN public.con_archivo_carga a ON a.id_archivo=i.id_archivo
                               WHERE i.id_jornada=%s''', (id_jornada,))
                archivos = cur.fetchall()
                cur.execute('''SELECT f.id_archivo, f.cuenta, f.concepto, f.valor, f.franquicia, f.correlation_id
                               FROM public.con_franquicia_resultado f
                               WHERE EXISTS (SELECT 1 FROM public.con_insumo_esperado i
                                             WHERE i.id_jornada=%s AND i.id_archivo=f.id_archivo)
                               ORDER BY f.id_franquicia_resultado''', (id_jornada,))
                fr = cur.fetchall()
                cur.execute('''SELECT h.id_archivo, h.cuenta, h.centro, h.concepto, h.valor_normalizado, h.tx_host, h.correlation_id
                               FROM public.con_host_resultado h
                               WHERE EXISTS (SELECT 1 FROM public.con_insumo_esperado i
                                             WHERE i.id_jornada=%s AND i.id_archivo=h.id_archivo)
                               ORDER BY h.id_host_resultado''', (id_jornada,))
                host = cur.fetchall()
                                # CONCILIA_COBERTURA_29_REPORTE_V1
                reporte = armar_reporte(
                    (j['id_jornada'], j['fecha_contable'], j['estado']),
                    archivos, fr, host
                )
                cobertura = construir_cobertura_cuentas(host)
                reporte['cobertura_contable_host'] = [
                    {
                        'cuenta': c['cuenta'],
                        'centro': c['centro'],
                        'descripcion': c['descripcion'],
                        'regla_consulta': c['regla_consulta'],
                        'estado': c['estado'],
                        'franquicia_relacionada': c['franquicia_relacionada'],
                        'proceso_cuadre': c['proceso_cuadre'],
                        'evidencia_homologacion': c['evidencia_homologacion'],
                        'certeza_homologacion': c['certeza_homologacion'],
                        'estado_homologacion': c['estado_homologacion'],
                        # CONCILIA_HOMOLOGACION_REPORTE_V3
                        'cantidad_movimientos': len(c['movimientos']),
                        'evidencias': [
                            {
                                'fuente': m.get('tx_host'),
                                'id_archivo': m.get('id_archivo'),
                                'valor_normalizado': (
                                    str(m['valor_normalizado'])
                                    if m.get('valor_normalizado') is not None
                                    else None
                                )
                            }
                            for m in c['movimientos']
                        ]
                    }
                    for c in cobertura
                ]

                # CONCILIA_V39_CLASIFICACION_FRANQUICIAS
                from app.services.fase2.clasificacion_franquicias_v39 import (
                    enriquecer_cobertura, resumen_catalogo,
                )
                reporte['cobertura_contable_host'] = enriquecer_cobertura(
                    reporte['cobertura_contable_host']
                )
                reporte['catalogo_franquicias_v39'] = {
                    'cantidades': resumen_catalogo(),
                    'certificado': False,
                    'nota': 'Clasificacion documental; no constituye cruce monetario.'
                }
                # CONCILIA_MONETARIO_HOST_V4
                from app.services.fase2.monetario_cuentas_host import (
                    calcular_monetario_host,
                )
                monetario = calcular_monetario_host(
                    j["id_jornada"],
                    [c["cuenta"] for c in
                     reporte["cobertura_contable_host"]],
                )
                for c in reporte["cobertura_contable_host"]:
                    c["monetario_host"] = monetario[c["cuenta"]]
                # CONCILIA_ORIGEN_MONETARIO_V14 - TOTALES INDEPENDIENTES POR INSUMO
                # CAET, CANT y DEPO se muestran como origen global; nunca se suman
                # entre si ni se atribuyen automaticamente a una cuenta contable.
                cur.execute("""
                    SELECT a.tipo_archivo, d.id_archivo,
                           COUNT(*) AS registros,
                           SUM(d.vl_total) AS vl_total,
                           SUM(d.vl_interc) AS vl_interc,
                           SUM(d.comision_op_exitosas) AS comisiones
                    FROM public.con_insumo_esperado i
                    JOIN public.con_archivo_carga a ON a.id_archivo = i.id_archivo
                    JOIN public.con_canje_detalle d ON d.id_archivo = a.id_archivo
                    WHERE i.id_jornada = %s
                      AND a.tipo_archivo IN ('CAET', 'CANT')
                    GROUP BY a.tipo_archivo, d.id_archivo
                    ORDER BY CASE a.tipo_archivo WHEN 'CAET' THEN 1 WHEN 'CANT' THEN 2 ELSE 9 END, d.id_archivo
                """, (id_jornada,))
                origen = [
                    {'insumo': x['tipo_archivo'], 'id_archivo': x['id_archivo'],
                     'registros': x['registros'],
                     'vl_total': str(x['vl_total']) if x['vl_total'] is not None else None,
                     'vl_interc': str(x['vl_interc']) if x['vl_interc'] is not None else None,
                     'comisiones': str(x['comisiones']) if x['comisiones'] is not None else None,
                     'homologado': False, 'certificado': False}
                    for x in cur.fetchall()
                ]
                cur.execute("""
                    SELECT a.tipo_archivo, d.id_archivo,
                           COUNT(*) AS registros,
                           SUM(CASE WHEN BTRIM(d.valor_total) ~ '^[0-9]+$'
                                    THEN BTRIM(d.valor_total)::numeric ELSE NULL END) AS vl_total,
                           SUM(CASE WHEN BTRIM(d.valor_intercambio) ~ '^[0-9]+(?:\\.[0-9]+)?$'
                                    THEN BTRIM(d.valor_intercambio)::numeric ELSE NULL END) AS vl_interc,
                           NULL::numeric AS comisiones
                    FROM public.con_insumo_esperado i
                    JOIN public.con_archivo_carga a ON a.id_archivo = i.id_archivo
                    JOIN public.con_depo_detalle d ON d.id_archivo = a.id_archivo
                    WHERE i.id_jornada = %s
                      AND a.tipo_archivo = 'DEPO'
                    GROUP BY a.tipo_archivo, d.id_archivo
                    ORDER BY d.id_archivo
                """, (id_jornada,))
                origen.extend(
                    {'insumo': x['tipo_archivo'], 'id_archivo': x['id_archivo'],
                     'registros': x['registros'],
                     'vl_total': str(x['vl_total']) if x['vl_total'] is not None else None,
                     'vl_interc': str(x['vl_interc']) if x['vl_interc'] is not None else None,
                     'comisiones': None,
                     'homologado': False, 'certificado': False}
                    for x in cur.fetchall()
                )
                reporte['origen_monetario_credibanco'] = origen
                # CONCILIA_ORIGEN_MONETARIO_DEPO_V1 - SOLO LECTURA, NO HOMOLOGACION
                cur.execute("""
                    SELECT a.tipo_archivo, d.id_archivo, d.cuenta AS concepto,
                           COUNT(*) AS registros,
                           SUM(CASE WHEN BTRIM(d.valor_total) ~ '^[0-9]+$'
                               THEN BTRIM(d.valor_total)::numeric ELSE NULL END) AS valor_total,
                           SUM(
    CASE
        WHEN BTRIM(d.valor_intercambio) ~ '^-?[0-9]+(?:\\.[0-9]+)?$'
        THEN BTRIM(d.valor_intercambio)::numeric
        ELSE NULL
    END
) AS valor_intercambio,
                           SUM(
    CASE
        WHEN BTRIM(d.valor_intercambio_2) ~ '^-?[0-9]+(?:\\.[0-9]+)?$'
        THEN BTRIM(d.valor_intercambio_2)::numeric
        ELSE NULL
    END
) AS valor_intercambio_2,
                           SUM(d.tasa_de_intercambio) AS tasa_intercambio
                    FROM public.con_insumo_esperado i
                    JOIN public.con_archivo_carga a ON a.id_archivo = i.id_archivo
                    JOIN public.con_depo_detalle d ON d.id_archivo = a.id_archivo
                    WHERE i.id_jornada = %s
                      AND a.tipo_archivo = 'DEPO'
                    GROUP BY a.tipo_archivo, d.id_archivo, d.cuenta
                    ORDER BY d.id_archivo, d.cuenta
                """, (id_jornada,))
                reporte['origen_monetario_depo'] = [
                    {'insumo': x['tipo_archivo'], 'id_archivo': x['id_archivo'],
                     'concepto': x['concepto'], 'registros': x['registros'],
                     'valor_total': str(x['valor_total']) if x['valor_total'] is not None else None,
                     'valor_intercambio': str(x['valor_intercambio']) if x['valor_intercambio'] is not None else None,
                     'valor_intercambio_2': str(x['valor_intercambio_2']) if x['valor_intercambio_2'] is not None else None,
                     'tasa_intercambio': str(x['tasa_intercambio']) if x['tasa_intercambio'] is not None else None,
                     'homologado': False, 'certificado': False}
                    for x in cur.fetchall()
                ]
                # CONCILIA_V14_ARCHIVOS_ORIGEN: asociación verificable para lectura bajo demanda
                reporte['insumos_archivo_origen'] = [
                    {'tipo_insumo': a['tipo_archivo'], 'id_archivo': a['id_archivo']}
                    for a in archivos if a['tipo_archivo'] in ('CAET', 'CANT')
                ]
                reporte['origen_monetario_nota'] = (
                    'Totales por archivo CAET/CANT/DEPO; no asignados a cuentas Host. '
                    'No se calculan diferencias sin correspondencia aprobada.'
                )
                # CONCILIA_V36_INTEGRACION_CALCULOS
                import json as _json
                from pathlib import Path as _Path
                from app.services.fase2.integracion_v36 import construir_cruces_v36
                _reglas = _json.loads((_Path(__file__).resolve().parents[1] / 'services' / 'fase2' / 'reglas_v36.json').read_text(encoding='utf-8'))['reglas']
                reporte['cruces_monetarios_v36'] = construir_cruces_v36(cur, id_jornada, _reglas)
                # CONCILIA_V38_PROYECCION_PERSISTIDA
                from app.services.fase2.proyeccion_credibanco_v38 import consultar as consultar_v38
                reporte['proyeccion_credibanco_v38'] = consultar_v38(cur, id_jornada)
                # CONCILIA_V37_COMPARACION_LITERAL
                from app.services.fase2.comparacion_literal_v37 import comparaciones_por_cuenta
                reporte['comparaciones_literales_no_homologadas'] = comparaciones_por_cuenta(fr, host)
                # CONCILIA_V44_FORMULAS_PG
                from app.services.fase2.conexion_formulas_v44 import ejecutar as _ejecutar_v44
                with connection() as conn_v44:
                    with conn_v44.cursor() as cur_v44:
                        cur_v44.execute("SET TRANSACTION READ ONLY")
                        reporte['formulas_credibanco_v44'] = _ejecutar_v44(cur_v44, id_jornada)
                # CONCILIA_V46_NORMALIZACION_UNIDADES
                from app.services.fase2.normalizacion_v46 import enriquecer as _enriquecer_v46
                reporte['formulas_credibanco_v46'] = _enriquecer_v46(reporte['formulas_credibanco_v44'])
                # CONCILIA_V74_AUDITORIA_FUENTES_READONLY
                from app.services.fase2.auditoria_fuentes_credibanco_v74 import auditar_fuentes_v74
                reporte['auditoria_fuentes_credibanco_v74'] = auditar_fuentes_v74(
                    cur, id_jornada, j['fecha_contable']
                )
                # CONCILIA_V72_CREDIBANCO_ESTADOS_ORIGINAL
                from app.services.fase2.estado_cuentas_credibanco_v72 import construir_estado_v72
                reporte['diagnostico_credibanco_v72'] = construir_estado_v72(
                    id_jornada,
                    j['fecha_contable'],
                    reporte['cobertura_contable_host'],
                    reporte['cruces_monetarios_v36'],
                    host,
                )

                return reporte
    except HTTPException:
        raise
    except Exception as exc:
        from psycopg import OperationalError
        if isinstance(exc, (OperationalError, KeyError)):
            raise HTTPException(status_code=503, detail='Consulta no disponible') from exc
        raise


# CONCILIA_V21_DIAGNOSTICO
@router.get('/{id_jornada}/diagnostico-homologacion-v21')
def diagnostico_homologacion_v21(id_jornada: int):
    from app.services.fase2.servicio_v21 import diagnosticar_jornada
    if id_jornada <= 0:
        raise HTTPException(status_code=422, detail='Jornada invalida')
    try:
        resultado = diagnosticar_jornada(id_jornada)
    except Exception:
        raise HTTPException(status_code=503, detail='No fue posible consultar el diagnostico')
    if resultado is None:
        raise HTTPException(status_code=404, detail='Jornada no encontrada')
    return resultado


# CONCILIA_V22_ENSAYO_AISLADO
@router.get('/ensayo-v22')
def ensayo_v22():
    from app.services.fase2.servicio_v22 import obtener_ensayo
    return obtener_ensayo()


# CONCILIA_V22_RUTA_INDEPENDIENTE
from fastapi import APIRouter

router_ensayo_v22 = APIRouter(
    prefix="/api/v1/ensayos",
    tags=["Ensayos no certificados"]
)

@router_ensayo_v22.get("/conciliacion-v22")
def conciliacion_ensayo_v22():
    from app.services.fase2.servicio_v22 import obtener_ensayo
    return obtener_ensayo()
