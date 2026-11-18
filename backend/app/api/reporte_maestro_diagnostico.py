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


# PRUEBA6606_API_V2: endpoint diagnostico, nunca certifica ni escribe.
@router.get('/6606/paridad-sintetica-maestro', include_in_schema=False)
def paridad_sintetica_maestro_6606():
    from decimal import Decimal
    from app.services.fase2.repositorio_pmd_inc58 import leer_jornada
    from app.services.fase2.integracion_redeban_host_inc68 import leer_host_jornada
    mapa = {'1.7':'196095001828','1.8':'196095001829',
            '1.5':'299095240','1.6':'299095508',
            '1.9':'299095866','1.4':'299095883'}
    esperado = {'1.7':Decimal('170000'),'1.8':Decimal('-60000'),
                '1.5':Decimal('80000'),'1.6':Decimal('-35000'),
                '1.9':Decimal('15000'),'1.4':Decimal('-200000')}
    pmd = leer_jornada(6606)
    fecha, host, estado = leer_host_jornada(6606)
    if str(fecha) != '2026-11-12' or estado != 'HOST_DISPONIBLE':
        raise HTTPException(409, 'Jornada o Host de prueba no disponible')
    niveles = {str(x['NIVEL']):x for x in pmd}
    if len(pmd) != 9 or len(niveles) != 9 or len(host) != 27:
        raise HTTPException(409, 'Conteos de prueba cambiaron')
    from collections import defaultdict
    # RECON_F2_005_TRES_HOST_ESTRUCTURADOS
    fuentes = ('HA22', 'HA26', 'HA32')
    netos = defaultdict(lambda: Decimal('0'))
    movimientos = defaultdict(int)

    for r in host:
        fuente = str(r['fuente'])
        if fuente not in fuentes:
            raise HTTPException(409, 'Fuente Host inesperada')

        if (
            str(r['fecha_contable']) != '2026-11-12'
            or str(r['centro']).zfill(4) != '0017'
        ):
            raise HTTPException(409, 'Host fuera de fecha o centro')

        clave = (str(r['cuenta']), fuente)
        netos[clave] += (
            Decimal(str(r['debe']))
            - Decimal(str(r['haber']))
        )
        movimientos[clave] += 1
    detalle=[]
    for nivel, cuenta in mapa.items():
        if nivel not in niveles: raise HTTPException(409, 'Nivel PMD faltante')
        p = Decimal(str(niveles[nivel]['TOTAL']))
        netos_cuenta = {
            fuente: netos.get((cuenta, fuente))
            for fuente in fuentes
        }

        if any(
            movimientos.get((cuenta, fuente), 0) == 0
            for fuente in fuentes
        ):
            raise HTTPException(
                409, 'Fuente Host faltante: ' + cuenta
            )

        if (
            p != esperado[nivel]
            or any(
                netos_cuenta[fuente] != esperado[nivel]
                for fuente in fuentes
            )
        ):
            raise HTTPException(
                409, 'La evidencia ya no coincide: ' + nivel
            )

        h = netos_cuenta['HA22']

        detalle.append({
            'nivel_pmd': nivel,
            'cuenta_host': cuenta,
            'neto_pmd': str(p),
            'neto_host': str(h),
            'netos_host': {
                fuente: str(netos_cuenta[fuente])
                for fuente in fuentes
            },
            'diferencia': str(p - h),
            'estado': 'COINCIDE_EN_PRUEBA'
        })
    pendientes=[]
    for nivel in ('1.1','1.2','1.3'):
        if nivel not in niveles: raise HTTPException(409, 'Pendiente PMD faltante')
        pendientes.append({'nivel_pmd':nivel,'total':str(niveles[nivel]['TOTAL']),
                           'estado':'SIN_HOMOLOGACION_DE_PRUEBA'})
    return {'id_jornada':6606,'fecha_contable':'2026-11-12',
            'modo':'SOLO_PRUEBAS','certificado':False,
            'detalle':detalle,'pendientes_pmd':pendientes}

# CONCILIA_6606_API_DETALLE_V3: consulta aislada de prueba, sin escritura ni certificacion.
@router.get('/6606/paridad-detalle-prueba', include_in_schema=False)
def paridad_detalle_prueba_6606():
    from decimal import Decimal, InvalidOperation
    from collections import defaultdict
    from app.services.fase2.repositorio_pmd_inc58 import leer_jornada
    from app.services.fase2.integracion_redeban_host_inc68 import leer_host_jornada
    from app.repositories.database import connection as conexion_bd
    mapa = {'1.7':'196095001828','1.8':'196095001829','1.5':'299095240',
            '1.6':'299095508','1.9':'299095866','1.4':'299095883'}
    esperados = {'1.7':'170000','1.8':'-60000','1.5':'80000','1.6':'-35000',
                 '1.9':'15000','1.4':'-200000'}
    with conexion_bd() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('SELECT fecha_contable FROM public.con_jornada WHERE id_jornada=%s',(6606,))
            jornada=cur.fetchone()
            if not jornada or str(jornada[0])!='2026-11-12': raise HTTPException(409,'Fecha de jornada no valida')
    pmd=leer_jornada(6606)
    fecha,host,estado=leer_host_jornada(6606)
    if str(fecha)!='2026-11-12' or estado!='HOST_DISPONIBLE' or len(pmd)!=9 or len(host)!=27:
        raise HTTPException(409,'Evidencia de prueba no disponible o modificada')
    niveles={str(f['NIVEL']):f for f in pmd}
    if len(niveles)!=9: raise HTTPException(409,'Niveles duplicados')
    por_cuenta=defaultdict(list)
    for r in host:
        if r.get('fuente')!='HA22': continue
        if str(r.get('fecha_contable'))!='2026-11-12' or str(r.get('centro')).zfill(4)!='0017':
            raise HTTPException(409,'Movimiento Host fuera de alcance')
        por_cuenta[str(r['cuenta'])].append(r)
    detalle=[]
    try:
        for nivel,cuenta in mapa.items():
            f=niveles[nivel]; debito=Decimal(str(f['DEBITO_NETO'])); credito=Decimal(str(f['CREDITO_NETO']))
            neto=debito-credito; movimientos=por_cuenta.get(cuenta,[])
            if not movimientos: raise HTTPException(409,'Sin movimientos Host para '+cuenta)
            neto_host=sum((Decimal(str(m['debe']))-Decimal(str(m['haber'])) for m in movimientos),Decimal('0'))
            if not all(x.is_finite() for x in (debito,credito,neto,neto_host)) or neto!=Decimal(esperados[nivel]) or neto_host!=neto or Decimal(str(f['TOTAL']))!=neto:
                raise HTTPException(409,'Importes de prueba cambiaron: '+nivel)
            detalle.append({'nivel_pmd':nivel,'cuenta_host':cuenta,'id_archivo_pmd':f['id_archivo'],
                'linea_pmd':f.get('numero_linea'),'debito_pmd':str(debito),'credito_pmd':str(credito),
                'neto_pmd':str(neto),'neto_host':str(neto_host),'diferencia':str(neto-neto_host),
                'estado':'COINCIDE_EN_PRUEBA','movimientos_host':[
                    {k:(str(m[k]) if m.get(k) is not None else None) for k in ('fuente','id_archivo','linea','fecha_contable','debe','haber')} for m in movimientos]})
    except (KeyError,InvalidOperation,TypeError,ValueError) as exc:
        raise HTTPException(409,'Evidencia de prueba invalida') from exc
    # RECON_F2_005_CIERRE_TRES_FUENTES_V2
    # Netos por cuenta y fuente; nunca sumar HA22/HA26/HA32 entre si.
    fuentes=('HA22','HA26','HA32')
    netos_fuentes=defaultdict(lambda: defaultdict(lambda: Decimal('0')))
    conteos_fuentes=defaultdict(lambda: defaultdict(int))
    for movimiento in host:
        fuente=str(movimiento.get('fuente',''))
        if fuente not in fuentes:
            continue
        if (str(movimiento.get('fecha_contable'))!='2026-11-12' or
                str(movimiento.get('centro')).zfill(4)!='0017'):
            raise HTTPException(409,'Movimiento Host fuera de fecha o centro')
        cuenta=str(movimiento['cuenta'])
        netos_fuentes[cuenta][fuente] += (Decimal(str(movimiento['debe'])) -
                                         Decimal(str(movimiento['haber'])))
        conteos_fuentes[cuenta][fuente] += 1
    for fila in detalle:
        cuenta=fila['cuenta_host']
        p=Decimal(fila['neto_pmd'])
        por_fuente={}
        for fuente in fuentes:
            cantidad=conteos_fuentes[cuenta][fuente]
            if not cantidad:
                por_fuente[fuente]={'neto':None,'diferencia':None,'movimientos':0}
            else:
                neto=netos_fuentes[cuenta][fuente]
                por_fuente[fuente]={'neto':str(neto),'diferencia':str(p-neto),
                                    'movimientos':cantidad}
        fila['fuentes_host']=por_fuente
        fila['resultado_monetario'] = (
            'PENDIENTE_CONCILIACION' if any(v['neto'] is None for v in por_fuente.values())
            else 'CONCILIADO' if all(Decimal(v['diferencia']) == 0 for v in por_fuente.values())
            else 'CON_DIFERENCIA'
        )
    pendientes=[{'nivel_pmd':n,'neto_pmd':str(niveles[n]['TOTAL']),'estado':'SIN_HOMOLOGACION_DE_PRUEBA'} for n in ('1.1','1.2','1.3')]
    return {'id_jornada':6606,'fecha_contable':'2026-11-12','modo':'SOLO_PRUEBAS',
            'certificado':False,'detalle':detalle,'pendientes_pmd':pendientes}
