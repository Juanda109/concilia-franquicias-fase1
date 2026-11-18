# Read-only synthetic Credibanco coverage for journey 3976.
from fastapi import APIRouter, HTTPException
from app.repositories.database import connection
router = APIRouter()
JORNADA=3976
FECHA='2026-10-15'
MARCA='CONCILIA_SYNC7_3976_TEST_V1'
TIPOS=('HA22','HA26','HA32','CAET','CANT','DEPO','CARTA_COMPENSACION')

def obtener_evidencia():
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('''SELECT i.tipo_insumo,a.id_archivo,a.nombre_archivo
                FROM public.con_insumo_esperado i
                JOIN public.con_archivo_carga a ON a.id_archivo=i.id_archivo
                WHERE i.id_jornada=%s AND a.fecha_contable=%s''',(JORNADA,FECHA))
            encontrados={t:(aid,nombre) for t,aid,nombre in cur.fetchall()}
            if set(TIPOS)-set(encontrados) or any(not encontrados[t][1].startswith(MARCA+'_') for t in TIPOS):
                raise HTTPException(status_code=409,detail='Escenario sintetico incompleto o archivos ajenos')
            ids={t:encontrados[t][0] for t in TIPOS}
            resultado=[]
            cur.execute('''SELECT tx_host,cuenta,COUNT(*),SUM(valor_debe),SUM(valor_haber)
                FROM public.con_host_resultado WHERE id_archivo=ANY(%s)
                GROUP BY tx_host,cuenta ORDER BY tx_host,cuenta''',([ids[t] for t in TIPOS[:3]],))
            for fuente,cuenta,cantidad,debe,haber in cur.fetchall():
                resultado.append(dict(insumo=fuente,cuenta=cuenta,concepto='EVIDENCIA_HOST',cantidad=cantidad,
                  valor_total=None,valor_intercambio=None,debe=str(debe) if debe is not None else None,
                  haber=str(haber) if haber is not None else None,unidad='VALOR_HOST',certificado=False))
            cur.execute('''SELECT tipo_archivo,COALESCE(cuenta,''),COUNT(*),SUM(vl_total),SUM(vl_interc)
                FROM public.con_canje_detalle WHERE id_archivo=ANY(%s)
                GROUP BY tipo_archivo,cuenta ORDER BY tipo_archivo,cuenta''',([ids['CAET'],ids['CANT']],))
            for tipo,cuenta,cantidad,total,interc in cur.fetchall():
                resultado.append(dict(insumo=tipo,cuenta=cuenta or None,concepto='CANJE_ORIGEN',cantidad=cantidad,
                  valor_total=str(total) if total is not None else None,valor_intercambio=str(interc) if interc is not None else None,
                  debe=None,haber=None,unidad='IMPORTE_ORIGEN',certificado=False))
            cur.execute('''SELECT linea_origen,tipo_movimiento,cod_oficina,indicador_cash_back,valor_total
                FROM public.con_depo_detalle WHERE id_archivo=%s ORDER BY linea_origen''',(ids['DEPO'],))
            from decimal import Decimal
            for linea,tipo,oficina,indicador,valor in cur.fetchall():
                concepto=('017-OP CNBS' if str(indicador or '').strip() in ('010','011','012','110','111','112')
                  else 'DEPOSITO_INTERNACIONAL' if tipo=='06' and oficina=='0090'
                  else 'DEPOSITO_NACIONAL' if tipo=='06' else 'OTRO_DEPO')
                texto=str(valor or '').strip()
                if not texto.isdigit(): raise HTTPException(status_code=422,detail='Valor DEPO crudo invalido')
                # CNB_CUENTA_1770_V1: correspondencia de cuenta; no certifica escala ni cruce.
                cuenta_depo = '196095001770' if concepto == '017-OP CNBS' else None
                resultado.append(dict(insumo='DEPO',cuenta=cuenta_depo,concepto=concepto,cantidad=1,
                  valor_total=str(Decimal(texto)),valor_intercambio=None,debe=None,haber=None,
                  linea_origen=linea,unidad='UNIDADES_CRUDAS',certificado=False))
            cur.execute('''SELECT linea_origen,concepto,valor_total,valor_depositos_electronicos
                FROM public.con_carta_compensacion_detalle WHERE id_archivo=%s ORDER BY linea_origen''',(ids['CARTA_COMPENSACION'],))
            for linea,concepto,total,depositos in cur.fetchall():
                resultado.append(dict(insumo='CARTA_COMPENSACION',cuenta=None,concepto=concepto,cantidad=1,
                  valor_total=str(total) if total is not None else None,valor_intercambio=None,
                  valor_depositos_electronicos=str(depositos) if depositos is not None else None,
                  debe=None,haber=None,linea_origen=linea,unidad='VALOR_CARTA',certificado=False))
    return {'id_jornada':JORNADA,'fecha_contable':FECHA,'escenario':'SINTETICO_NO_CERTIFICADO',
      'total_insumos':len(TIPOS),'filas':resultado,'certificado_monetario':False}

@router.get('/api/v1/jornadas/3976/credibanco-sintetico')
def credibanco_sintetico():
    return obtener_evidencia()


# SIM3976_V2: comprobacion estrictamente sintetica, sin certificacion productiva.
@router.get('/api/v1/jornadas/3976/cuadre-simulado')
def cuadre_simulado_3976():
    from decimal import Decimal
    from collections import defaultdict
    evidencia = obtener_evidencia()
    filas = evidencia['filas']
    cuentas = ('196095001838', '196095001839')
    fuentes = ('HA22', 'HA26', 'HA32')
    resultados = []
    for cuenta in cuentas:
        host = {}
        for fuente in fuentes:
            hallados = [f for f in filas if f['insumo'] == fuente and f['cuenta'] == cuenta]
            if len(hallados) != 1 or hallados[0]['debe'] is None or hallados[0]['haber'] is None:
                raise HTTPException(status_code=409, detail='Host sintetico incompleto')
            f = hallados[0]
            debe, haber = Decimal(f['debe']), Decimal(f['haber'])
            host[fuente] = {'debe': str(debe), 'haber': str(haber), 'neto': str(debe-haber)}
        origen = {}
        for tipo in ('CAET','CANT'):
            hallados = [f for f in filas if f['insumo'] == tipo and f['cuenta'] == cuenta]
            if len(hallados) != 1 or hallados[0]['valor_total'] is None:
                raise HTTPException(status_code=409, detail='Canje sintetico incompleto')
            origen[tipo] = Decimal(hallados[0]['valor_total'])
        concepto = 'DEPOSITO_NACIONAL' if cuenta.endswith('838') else 'DEPOSITO_INTERNACIONAL'
        depo = [f for f in filas if f['insumo'] == 'DEPO' and f['concepto'] == concepto]
        if len(depo) != 1:
            raise HTTPException(status_code=409, detail='DEPO sintetico incompleto')
        depo_crudo = Decimal(depo[0]['valor_total'])
        depo_prueba = depo_crudo / Decimal('100')  # Escala de prueba, NO homologacion.
        referencia = origen['CAET']  # CANT es verificacion independiente, no sumando.
        netos = {fuente: Decimal(host[fuente]['neto']) for fuente in fuentes}
        ok = (origen['CANT'] == referencia and depo_prueba == referencia
              and all(n == referencia for n in netos.values()))
        resultados.append({'cuenta': cuenta, 'concepto': concepto,
            'valor_franquicia': str(referencia), 'caet': str(origen['CAET']),
            'cant': str(origen['CANT']), 'depo_crudo': str(depo_crudo),
            'depo_escala_prueba': str(depo_prueba), 'host': host,
            'total_host': str(netos['HA22']),
            'diferencia': str(referencia - netos['HA22']),
            'estado': 'OK_SIMULADO' if ok else 'DIFERENCIA_SIMULADA'})
    cartas = [f for f in filas if f['insumo'] == 'CARTA_COMPENSACION']
    if len(cartas) != 1 or cartas[0]['valor_total'] is None:
        raise HTTPException(status_code=409, detail='Carta sintetica incompleta')
    total = sum((Decimal(r['valor_franquicia']) for r in resultados), Decimal('0'))
    carta = Decimal(cartas[0]['valor_total'])
    carta_ok = carta == total
    if not carta_ok:
        for r in resultados:
            r['estado'] = 'DIFERENCIA_SIMULADA'
    return {'id_jornada': 3976, 'escenario': 'SINTETICO_NO_CERTIFICADO',
        'certificado_monetario': False, 'escala_depo': '1/100_SOLO_PRUEBA',
        'filas': resultados, 'carta_total': str(carta), 'total_referencia': str(total),
        'carta_coincide': carta_ok,
        'ok_simulados': sum(r['estado'] == 'OK_SIMULADO' for r in resultados)}

# CONCILIA_CARTA_DESGLOSE_3976_V1: lectura de registros de Carta con trazabilidad.
@router.get('/api/v1/jornadas/3976/carta-desglose')
def carta_desglose_3976():
    # Conserva la proteccion del escenario sintetico existente.

    # CONCILIA_CARTA_DOS_HOJAS_3976_V1
    hojas_carta = (
        "carta compensacion 224A",
        "CAI224AS",
    )
    obtener_evidencia()
    from decimal import Decimal
    campos = ('valor_principal','valor_proceso','valor_financiacion',
              'valor_fotocopias','valor_red','valor_depositos_electronicos',
              'valor_total','valor_outgoing','valor_incoming','factor_compra','factor_venta')
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute("""SELECT d.id_archivo, a.nombre_archivo, d.linea_origen,
                d.seccion, d.concepto, d.motivo_codigo, d.es_control, d.lado,
                d.valor_principal,d.valor_proceso,d.valor_financiacion,
                d.valor_fotocopias,d.valor_red,d.valor_depositos_electronicos,
                d.valor_total,d.valor_outgoing,d.valor_incoming,
                d.factor_compra,d.factor_venta
                FROM public.con_carta_compensacion_detalle d
                JOIN public.con_archivo_carga a ON a.id_archivo=d.id_archivo
                JOIN public.con_insumo_esperado i ON i.id_archivo=d.id_archivo
                WHERE i.id_jornada=%s AND i.tipo_insumo='CARTA_COMPENSACION'
                  AND a.fecha_contable=%s
                ORDER BY d.id_archivo,d.linea_origen""", (JORNADA,FECHA))
            filas=[]
            for r in cur.fetchall():
                importes={campo:(str(v) if v is not None else None)
                         for campo,v in zip(campos,r[8:])}
                filas.append({'id_archivo':r[0],'nombre_archivo':r[1],
                    'linea_origen':r[2],'seccion':r[3],'concepto':r[4],
                    'motivo_codigo':r[5],'es_control':r[6],'lado':r[7],
                    'importes':importes})
    return {'id_jornada':JORNADA,'fecha_contable':FECHA,
            'hoja_origen_disponible':False,'certificado_monetario':False,
            'filas':filas}
