"""Pruebas de invariantes F2 Credibanco, sin BD ni Excel en ejecucion."""
from decimal import Decimal
import inspect
import pytest

from app.core.cierre_credibanco_v67 import (
    COMISIONES_L3, agrupar_depo, agrupar_host, calcular_l3_canje,
    calcular_l5_carta, construir_cierre, control_l8, control_posicion_carta,
    decimal_exacto,
)


def carta(seccion, motivo, *, principal=None, red=None, lado=None, control=True,
          archivo=4, cantidad=1):
    return dict(id_archivo=archivo, seccion=seccion, motivo_codigo=motivo,
                valor_principal=principal, valor_red=red, lado=lado,
                es_control=control, cantidad=cantidad)


def canje(comision, *, concepto=None, cod_error="00", tx="02", cantidad=1, id_archivo=2,
          nulos=0):
    return dict(id_archivo=id_archivo, cuentas_comisiones=concepto or sorted(COMISIONES_L3)[0],
                total_comision=comision, cod_error=cod_error, tx=tx,
                cantidad=cantidad, nulos_comision=nulos)


def metadata(faltantes=(), *, duplicado=None, fecha_error=None):
    fuentes = ("CAET", "CANT", "DEPO", "CARTA_COMPENSACION", "HA22", "HA26", "HA32")
    archivos = [dict(tipo_archivo=t, id_archivo=i+1, fecha_contable="2026-10-23",
                estado_archivo="PROCESADO", estado_insumo="PROCESADO")
                for i, t in enumerate(fuentes) if t not in faltantes]
    if duplicado:
        archivos.append({**next(a for a in archivos if a['tipo_archivo']==duplicado), 'id_archivo': 100})
    if fecha_error:
        next(a for a in archivos if a['tipo_archivo']==fecha_error)['fecha_contable'] = '2026-10-22'
    return archivos


def reporte(*, archivos=None, cartas=None, canjes=None, depos=None, hosts=None, regla=None):
    return construir_cierre(jornada={'id_jornada':2590,'fecha_contable':'2026-10-23'},
        archivos=metadata() if archivos is None else archivos,
        canje=[] if canjes is None else canjes, depo=[] if depos is None else depos,
        carta=[] if cartas is None else cartas, host=[] if hosts is None else hosts,
        aprobacion_l8=regla)


def test_carta_neta_igual_control_no_certifica():
    r=control_posicion_carta([carta('CAI0224A','POSICION_NETA',principal='27497216407'),
         carta('CAI0228A','POSICION_NETA',principal='27497216407')])
    assert r['estado']=='CUADRA' and r['diferencia']=='0' and not r['certificado']


def test_carta_neta_diferencia_no_cuadra():
    r=control_posicion_carta([carta('CAI0224A','POSICION_NETA',principal='10'),
         carta('CAI0228A','POSICION_NETA',principal='9.50')])
    assert r['estado']=='DESCUADRE' and r['diferencia']=='0.50'


def test_carta_neta_duplicada_bloquea():
    a=carta('CAI0224A','POSICION_NETA',principal='1')
    b=carta('CAI0228A','POSICION_NETA',principal='1')
    assert control_posicion_carta([a,a,b])['estado']=='FALTA_O_DUPLICA_POSICION_NETA'
    assert control_posicion_carta([{**a,'cantidad':2},b])['estado']=='CONTROL_DUPLICADO'


def test_carta_neta_faltante_bloquea():
    assert control_posicion_carta([carta('CAI0224A','POSICION_NETA',principal='1')])['estado']=='FALTA_O_DUPLICA_POSICION_NETA'


def test_carta_l5_usa_g_no_i():
    r=calcular_l5_carta([carta('CAI0224A','TOTAL_CANJE_RECIBIDO',lado='A_CARGO',
                       principal='3787450675',red='52777008')],4)
    assert r['valor']=='52777008'
    assert r['campo_persistido']=='valor_red' and not r['certificado']


def test_carta_l5_control_duplicado_y_faltante_bloquea():
    a=carta('CAI0224A','TOTAL_CANJE_RECIBIDO',lado='A_CARGO',red='5')
    assert calcular_l5_carta([a,a],4)['estado']=='FALTA_O_DUPLICA_TOTAL_CARGO'
    assert calcular_l5_carta([carta('CAI0224A','TOTAL_CANJE_RECIBIDO',lado='A_CARGO',red='5',control=False)],4)['valor'] is None


def test_l3_suma_solo_dos_conceptos_y_no_total():
    filas=[canje('100'),canje('50',concepto=sorted(COMISIONES_L3)[1],id_archivo=3),
           canje('100000',concepto='SIN_REGLA',id_archivo=2)]
    r=calcular_l3_canje(filas,{2,3})
    assert r['valor']=='150' and r['grupos']==2 and set(r['archivos'])=={2,3}


def test_l3_no_homologa_codigo_error_s():
    assert calcular_l3_canje([canje('100',cod_error='S')],{2})['valor'] is None


def test_l3_no_suma_lineas_control():
    assert calcular_l3_canje([canje('100',tx='Totales')],{2})['estado']=='CONTROL_INCLUIDO_EN_COMISIONES'


def test_l3_sin_valor_no_es_cero():
    assert calcular_l3_canje([canje(None,nulos=1)],{2})['estado']=='COMISION_INCOMPLETA'


def test_l8_sin_l6_no_calcula():
    l3={'estado':'CALCULADO_SIN_ESCALA_HOMOLOGADA','valor':'100'}
    l5={'estado':'CALCULADO_COMPONENTE_G','valor':'150'}
    assert control_l8(l3,l5)['l8'] is None
    assert control_l8(l3,l5,{'estado':'PENDIENTE'})['l8'] is None


def test_l8_con_evidencia_homologada_calcula_sin_certificar():
    l3={'estado':'CALCULADO_SIN_ESCALA_HOMOLOGADA','valor':'10000'}
    l5={'estado':'CALCULADO_COMPONENTE_G','valor':'200'}
    params={'estado':'APROBADA','version':'F2-CANJE-001','evidencia':'acta','moneda':'COP',
            'fuente_l6':'carta_224','escala_canje':'100','escala_carta':'1','l6':'50'}
    r=control_l8(l3,l5,params)
    assert r['l8']=='50' and r['certificado'] is False


def test_l8_escala_no_validada_no_inferida():
    with pytest.raises(ValueError,match='Escalas'):
        control_l8({'estado':'CALCULADO_SIN_ESCALA_HOMOLOGADA','valor':'10'},
            {'estado':'CALCULADO_COMPONENTE_G','valor':'20'},
            {'estado':'APROBADA','version':'1','evidencia':'A','moneda':'COP',
             'fuente_l6':'X','escala_canje':'0','escala_carta':'1','l6':'0'})


def test_depo_nacional_838_internacional_839_sin_homologar():
    a={'id_archivo':4,'concepto':'017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS',
       'tipo_movimiento':'06','cantidad':3,'valores_invalidos':0,'valor_total_crudo':'3000',
       'tasa_intercambio_cruda':'100'}
    b={**a,'concepto':'017-VR. DEPOSITOS ELECTRONICOS INTERNACIONAL CONSIGNADOS'}
    r=agrupar_depo([a,b],{4})
    assert [x['cuenta_host_candidata'] for x in r]==['196095001838','196095001839']
    assert all(x['estado']=='PENDIENTE_ESCALA_SIGNO_Y_FUENTE_HOST' for x in r)


def test_depo_control_y_valor_invalido_bloqueado():
    a={'id_archivo':4,'concepto':'', 'tipo_movimiento':'05', 'cantidad':1,
       'valores_invalidos':0,'valor_total_crudo':None,'tasa_intercambio_cruda':None}
    b={**a,'tipo_movimiento':'06','valores_invalidos':1}
    r=agrupar_depo([a,b],{4})
    assert r[0]['estado']=='CONTROL_NO_TRANSACCIONAL'
    assert r[1]['estado']=='PENDIENTE_CLASIFICACION_O_DATOS'


def test_host_no_suma_fuentes_y_bloquea_sinteticos():
    h=[{'id_archivo':5,'tx_host':'HA22','cuenta':'299095302','centro':'17',
        'concepto':'PRUEBA SINTETICA - NO CONCILIAR','fecha_contable':'2026-10-23',
        'cantidad':1,'incompletos':0,'debe':Decimal('11747139'),'haber':Decimal(0)},
       {'id_archivo':6,'tx_host':'HA26','cuenta':'299095302','centro':'0017',
        'concepto':'PRUEBA SINTETICA - NO CONCILIAR','fecha_contable':'2026-10-23',
        'cantidad':1,'incompletos':0,'debe':Decimal('11747389'),'haber':Decimal(0)}]
    x=agrupar_host(h,{5,6})
    assert len(x)==2 and [r['neto_debe_menos_haber'] for r in x]==['11747139','11747389']
    assert all(r['estado']=='BLOQUEADO_SINTETICO' for r in x)


def test_host_centro_con_punto_final_normaliza_igual_que_17():
    # CEDESTIN llega con un punto final en los HA22/26/32 observados
    # ("17." en vez de "17") - debe agruparse con la misma cuenta/centro,
    # no quedar como un centro distinto.
    h=[{'id_archivo':5,'tx_host':'HA22','cuenta':'299095302','centro':'17.',
        'concepto':'INTERFAZ MP2','fecha_contable':'2026-10-23',
        'cantidad':1,'incompletos':0,'debe':Decimal('100'),'haber':Decimal(0)}]
    r=agrupar_host(h,{5})
    assert len(r)==1
    assert r[0]['centro']=='0017'


def test_host_neto_no_calcula_con_nulos():
    h=[{'id_archivo':5,'tx_host':'HA22','cuenta':'299095302','centro':'0017',
        'concepto':None,'fecha_contable':'2026-10-23','cantidad':1,'incompletos':1,
        'debe':None,'haber':None}]
    assert agrupar_host(h,{5})[0]['neto_debe_menos_haber'] is None


def test_reporte_control_carta_cuadra_pero_no_certifica():
    c=[carta('CAI0224A','POSICION_NETA',principal='100'),
       carta('CAI0228A','POSICION_NETA',principal='100'),
       carta('CAI0224A','TOTAL_CANJE_RECIBIDO',lado='A_CARGO',red='50')]
    r=reporte(cartas=c,canjes=[canje('10',id_archivo=1),canje('20',id_archivo=2)])
    assert r['carta_posicion_neta']['estado']=='CUADRA'
    assert r['control_canje_carta']['L5_carta_componente_G']['valor']=='50'
    assert r['control_canje_carta']['L8_diferencia']['l8'] is None
    assert r['cruces_host_credibanco_certificados']==[] and r['certificado'] is False


def test_reporte_faltan_depo_carta_no_crea_cruces():
    r=reporte(archivos=metadata(faltantes=('DEPO','CARTA_COMPENSACION')))
    assert any(p['codigo']=='INSUMO_DEPO_FALTANTE' for p in r['pendientes'])
    assert r['control_canje_carta']['L5_carta_componente_G']['valor'] is None
    assert r['certificado'] is False


def test_reporte_rechaza_fecha_inconsistente_y_archivos_duplicados():
    r=reporte(archivos=metadata(duplicado='CAET',fecha_error='CANT'))
    assert any(p['codigo']=='INSUMO_CAET_ARCHIVOS_MULTIPLES' for p in r['pendientes'])
    assert any(p['codigo']=='INSUMO_CANT_FECHA_O_ESTADO_INCONSISTENTE' for p in r['pendientes'])
    assert r['control_canje_carta']['L3_comisiones_canje']['valor'] is None


def test_no_solo_estandar_y_sin_importacion_excel_en_motor():
    import app.core.cierre_credibanco_v67 as f2
    import app.repositories.cierre_credibanco as pg
    src=inspect.getsource(f2)+'\n'+inspect.getsource(pg)
    assert 'openpyxl' not in src and 'load_workbook(' not in src
    assert 'UPDATE public.' not in src and 'INSERT INTO public.' not in src


def test_decimales_no_admiten_flotantes_ni_nan():
    for v in (1.5, True, 'NaN', 'Infinity'):
        with pytest.raises(ValueError): decimal_exacto(v,'prueba')


def regla_aprobada(**cambios):
    r = dict(id_regla='CB-302-01',estado='APROBADA',version='2026-11-04-01',
        evidencia_aprobacion='acta-contable',insumo='CANT',
        concepto='017-CANJE RECIBIDO TARJETA CREDITO PAGOS',
        tx='04', campo_importe='total_valor',
        cuenta_host='299095302', centro_host='0017', fuente_host='HA22',
        moneda='COP',naturaleza_host='DEBE_MENOS_HABER',factor_signo=1,
        escala_origen='100',tolerancia='0',fechas_host_validas=['2026-10-23'])
    r.update(cambios)
    return r


def insumos_cruce():
    canjes=[dict(id_archivo=2,tipo_archivo='CANT',fecha_contable='2026-10-23',
                 cuenta='017-CANJE RECIBIDO TARJETA CREDITO PAGOS',
                 cuentas_comisiones='',tx='04',cod_error='00',cantidad=2,
                 total_valor=Decimal('10000'),total_intercambio=Decimal('8000'),
                 total_comision=None,nulos_total=0,nulos_interc=0,nulos_comision=2)]
    hosts=[dict(id_archivo=5,tx_host='HA22',cuenta='299095302',centro='0017',
                concepto='REAL',fecha_contable='2026-10-23',cantidad=1,
                incompletos=0,debe=Decimal('100'),haber=Decimal('0'))]
    return canjes,hosts


def test_regla_aprobada_calcula_diferencia_no_certificada():
    c,h=insumos_cruce()
    r=reporte(canjes=c,hosts=h,regla=None)  # sin reglas: solo evidencia
    assert r['cruces_host_credibanco_diagnosticos']==[]
    r=construir_cierre(jornada={'id_jornada':2590,'fecha_contable':'2026-10-23'},
          archivos=metadata(),canje=c,depo=[],carta=[],host=h,
          reglas_cruce=[regla_aprobada()])
    x=r['cruces_host_credibanco_diagnosticos'][0]
    assert x['valor_franquicia']=='100'
    assert x['valor_host']=='100'
    assert x['diferencia']=='0'
    assert x['estado']=='COINCIDE_DIAGNOSTICO_NO_CERTIFICADO'
    assert r['certificado'] is False


def test_regla_diferencia_en_monto_versionado():
    c,h=insumos_cruce()
    h[0]['debe']=Decimal('105')
    r=construir_cierre(jornada={'id_jornada':2590,'fecha_contable':'2026-10-23'},
          archivos=metadata(),canje=c,depo=[],carta=[],host=h,
          reglas_cruce=[regla_aprobada()])
    x=r['cruces_host_credibanco_diagnosticos'][0]
    assert x['diferencia']=='-5'
    assert x['estado']=='DIFERENCIA_DIAGNOSTICA_NO_CERTIFICADA'


def test_regla_sintetica_bloquea_cruce():
    c,h=insumos_cruce()
    h[0]['concepto']='PRUEBA SINTETICA - NO CONCILIAR'
    r=construir_cierre(jornada={'id_jornada':2590,'fecha_contable':'2026-10-23'},
          archivos=metadata(),canje=c,depo=[],carta=[],host=h,
          reglas_cruce=[regla_aprobada()])
    assert r['cruces_host_credibanco_diagnosticos'][0]['diferencia'] is None
    assert r['cruces_host_credibanco_diagnosticos'][0]['estado']=='HOST_NO_VALIDADO_O_SINTETICO'


def test_regla_fecha_host_pendiente_bloquea():
    c,h=insumos_cruce()
    r=construir_cierre(jornada={'id_jornada':2590,'fecha_contable':'2026-10-23'},
          archivos=metadata(),canje=c,depo=[],carta=[],host=h,
          reglas_cruce=[regla_aprobada(fechas_host_validas=['2026-10-22'])])
    assert r['cruces_host_credibanco_diagnosticos'][0]['estado']=='FECHA_HOST_NO_COINCIDE'


def test_regla_no_aprobada_calcula_pero_queda_marcada_sin_aprobar():
    # A pedido explicito: el motor calcula igual sin aprobacion formal, pero
    # el resultado nunca se confunde con uno aprobado/certificado - viaja
    # "aprobada": False y certificado sigue False.
    c,h=insumos_cruce()
    r=construir_cierre(jornada={'id_jornada':2590,'fecha_contable':'2026-10-23'},
          archivos=metadata(),canje=c,depo=[],carta=[],host=h,
          reglas_cruce=[regla_aprobada(estado='PENDIENTE_VALIDACION',
                                        version=None,evidencia_aprobacion=None)])
    x=r['cruces_host_credibanco_diagnosticos'][0]
    assert x['estado']=='COINCIDE_DIAGNOSTICO_NO_CERTIFICADO'
    assert x['diferencia']=='0'
    assert x['aprobada'] is False
    assert x['certificado'] is False
    assert r['certificado'] is False
    assert r['cruces_host_credibanco_certificados']==[]


def test_regla_aprobada_formalmente_marca_aprobada_true():
    c,h=insumos_cruce()
    r=construir_cierre(jornada={'id_jornada':2590,'fecha_contable':'2026-10-23'},
          archivos=metadata(),canje=c,depo=[],carta=[],host=h,
          reglas_cruce=[regla_aprobada()])
    assert r['cruces_host_credibanco_diagnosticos'][0]['aprobada'] is True


def test_regla_sin_campos_minimos_sigue_bloqueada_aunque_no_requiera_aprobacion():
    # Sin aprobacion no significa sin validar: si moneda/escala/signo/fechas
    # no estan definidos, el motor sigue sin poder calcular nada util.
    c,h=insumos_cruce()
    r=construir_cierre(jornada={'id_jornada':2590,'fecha_contable':'2026-10-23'},
          archivos=metadata(),canje=c,depo=[],carta=[],host=h,
          reglas_cruce=[regla_aprobada(estado='PENDIENTE_VALIDACION',
                                        version=None,evidencia_aprobacion=None,
                                        moneda=None)])
    x=r['cruces_host_credibanco_diagnosticos'][0]
    assert x['estado']=='MONEDA_O_NATURALEZA_NO_APROBADA'
    assert x['aprobada'] is False
    assert x['diferencia'] is None


def test_regla_falta_escala_falla_cerrado():
    c,h=insumos_cruce()
    from app.core.cierre_credibanco_v67 import evaluar_reglas_cruce, agrupar_host
    with pytest.raises(ValueError,match='escala_origen'):
        evaluar_reglas_cruce([regla_aprobada(escala_origen=None)],
            canje=c,depo=[],carta=[],host=agrupar_host(h,{5}),
            ids_validos={'CANT':2,'HA22':5})


def test_regla_no_suma_host_ha22_con_ha26():
    c,h=insumos_cruce()
    h.append({**h[0], 'id_archivo':6, 'tx_host':'HA26','debe':Decimal('99999')})
    r=construir_cierre(jornada={'id_jornada':2590,'fecha_contable':'2026-10-23'},
          archivos=metadata(),canje=c,depo=[],carta=[],host=h,
          reglas_cruce=[regla_aprobada()])
    assert r['cruces_host_credibanco_diagnosticos'][0]['valor_host']=='100'
    assert r['certificado'] is False


def test_no_se_acepta_identidad_archivo_tipo_incorrecta():
    c,h=insumos_cruce()
    c[0]['tipo_archivo']='CAET'
    r=construir_cierre(jornada={'id_jornada':2590,'fecha_contable':'2026-10-23'},
          archivos=metadata(),canje=c,depo=[],carta=[],host=h,
          reglas_cruce=[regla_aprobada()])
    assert any(x['codigo']=='CANJE_FILA_INCONSISTENTE' for x in r['pendientes'])
    assert r['cruces_host_credibanco_diagnosticos'][0]['diferencia'] is None


def test_regla_ids_duplicados_prohibidos():
    from app.core.cierre_credibanco_v67 import evaluar_reglas_cruce
    with pytest.raises(ValueError, match='duplicado'):
        evaluar_reglas_cruce([regla_aprobada(),regla_aprobada()],
           canje=[],depo=[],carta=[],host=[],ids_validos={})


def test_l3_ausencia_de_conceptos_no_se_infiere_cero():
    r = calcular_l3_canje([], {2, 3})
    assert r["valor"] is None
    assert r["estado"] == "SIN_CONCEPTOS_L3"


def test_depo_importes_incompletos_no_se_publican_como_candidato_valido():
    r = agrupar_depo([dict(id_archivo=4, concepto="017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS",
       tipo_movimiento="06", cantidad=2, valores_invalidos=0, nulos_tasa=1,
       valor_total_crudo="300", tasa_intercambio_cruda="20")], {4})
    assert r[0]["estado"] == "PENDIENTE_CLASIFICACION_O_DATOS"
    assert r[0]["nulos_tasa"] == 1


# Evidencia documental L6: no aprueba unidades ni habilita L8.
def _filas_evidencia_l6():
    comun = {
        "id_archivo": 4572,
        "nombre_archivo": "carta 09-11-2026.xlsx",
        "checksum_sha256": "f53223efba4821def4f50f6983a9a30db76596a45af201d4b336e21a862ceb7d",
        "fecha_contable": "2026-11-09",
    }
    return [
        {
            **comun, "linea_origen": 9, "seccion": "CAI0228A",
            "motivo_codigo": "CONCEPTO_CONTROL_CAI228A", "es_control": True,
            "lado": "A_FAVOR", "concepto": "DEPOSITOS ELECTRONICOS",
            "valor_principal": "2963074106", "valor_depositos_electronicos": None,
        },
        {
            **comun, "linea_origen": 18, "seccion": "CAI0224A",
            "motivo_codigo": "CONCEPTO_CANJE_ENVIADO", "es_control": False,
            "lado": "A_FAVOR", "concepto": "CLASICA BBVA",
            "valor_principal": "-74185206", "valor_depositos_electronicos": "2963074106",
        },
    ]


def test_l6_evidencia_coincidente_no_aprueba_ni_certifica():
    from app.core.cierre_credibanco_v67 import validar_evidencia_l6
    r = validar_evidencia_l6(_filas_evidencia_l6(), 4572, "2026-11-09")
    assert r["estado"] == "EVIDENCIA_L6_COINCIDENTE_PENDIENTE_APROBACION"
    assert r["valor"] == "2963074106"
    assert r["diferencia"] == "0"
    assert r["aprobacion_funcional"] == "PENDIENTE"
    assert r["certificado"] is False


def test_l6_evidencia_faltante_bloquea():
    from app.core.cierre_credibanco_v67 import validar_evidencia_l6
    filas = _filas_evidencia_l6()[:1]
    r = validar_evidencia_l6(filas, 4572, "2026-11-09")
    assert r["estado"] == "FUENTE_L6_FALTANTE"
    assert r.get("valor") is None


def test_l6_evidencia_duplicada_bloquea():
    from app.core.cierre_credibanco_v67 import validar_evidencia_l6
    filas = _filas_evidencia_l6()
    filas.append(dict(filas[0]))
    r = validar_evidencia_l6(filas, 4572, "2026-11-09")
    assert r["estado"] == "FUENTE_L6_DUPLICADA"
    assert r.get("valor") is None


def test_l6_evidencia_importes_diferentes_bloquea():
    from app.core.cierre_credibanco_v67 import validar_evidencia_l6
    filas = _filas_evidencia_l6()
    filas[1]["valor_depositos_electronicos"] = "2963074107"
    r = validar_evidencia_l6(filas, 4572, "2026-11-09")
    assert r["estado"] == "IMPORTES_L6_NO_COINCIDEN"
    assert r.get("valor") is None
    assert r["diferencia"] == "-1"


def test_l6_evidencia_fecha_incorrecta_bloquea():
    from app.core.cierre_credibanco_v67 import validar_evidencia_l6
    filas = _filas_evidencia_l6()
    filas[1]["fecha_contable"] = "2026-11-08"
    r = validar_evidencia_l6(filas, 4572, "2026-11-09")
    assert r["estado"] == "FUENTE_L6_INCONSISTENTE"
    assert r.get("valor") is None


def test_l6_evidencia_concepto_incorrecto_bloquea():
    from app.core.cierre_credibanco_v67 import validar_evidencia_l6
    filas = _filas_evidencia_l6()
    filas[0]["concepto"] = "ADQUIRENCIA MASTERCARD"
    r = validar_evidencia_l6(filas, 4572, "2026-11-09")
    assert r["estado"] == "FUENTE_L6_INCONSISTENTE"
    assert r.get("valor") is None


def test_l6_evidencia_checksum_diferente_bloquea():
    from app.core.cierre_credibanco_v67 import validar_evidencia_l6
    filas = _filas_evidencia_l6()
    filas[1]["checksum_sha256"] = "otro-checksum"
    r = validar_evidencia_l6(filas, 4572, "2026-11-09")
    assert r["estado"] == "CHECKSUM_L6_NO_COINCIDE"
    assert r.get("valor") is None


def test_l6_evidencia_archivo_incorrecto_bloquea():
    from app.core.cierre_credibanco_v67 import validar_evidencia_l6
    filas = _filas_evidencia_l6()
    r = validar_evidencia_l6(filas, 9999, "2026-11-09")
    assert r["estado"] == "FUENTE_L6_FALTANTE"
    assert r.get("valor") is None


def test_totales_diagnosticos_canje_provienen_de_persistencia_y_separan_importes():
    c = [
        dict(id_archivo=1, tipo_archivo='CAET', fecha_contable='2026-10-23',
             cuenta='017-CANJE RECIBIDO TARJETA CREDITO PAGOS', cuentas_comisiones='',
             tx='02', cod_error='00', cantidad=2, total_valor=Decimal('300'),
             total_intercambio=Decimal('200'), nulos_total=0, nulos_interc=0,
             total_comision=None, nulos_comision=0),
        dict(id_archivo=2, tipo_archivo='CANT', fecha_contable='2026-10-23',
             cuenta='017-CANJE RECIBIDO TARJETA CREDITO PAGOS', cuentas_comisiones='',
             tx='04', cod_error='00', cantidad=2, total_valor=Decimal('100'),
             total_intercambio=Decimal('50'), nulos_total=0, nulos_interc=0,
             total_comision=None, nulos_comision=0),
    ]
    r = construir_cierre(jornada={'id_jornada':2590,'fecha_contable':'2026-10-23'},
        archivos=metadata(), canje=c, depo=[], carta=[], host=[])
    total = next(x for x in r['totales_diagnosticos']
                 if x['A'] == '017-CANJE RECIBIDO TARJETA CREDITO PAGOS')
    assert total['B'] == 4
    assert total['C'] == '250'
    assert total['D'] == '400'
    assert set(total['insumos']) == {'CAET', 'CANT'}
    assert set(total['archivos']) == {1, 2}
