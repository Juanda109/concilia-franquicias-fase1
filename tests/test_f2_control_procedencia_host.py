from app.services.fase2.control_procedencia_host import evaluar_procedencia, BLOQUEADO, NO_VERIFICADO, VERIFICADO


def fila(tipo='HA22', **kwargs):
    return dict(tx_host=tipo, id_host_resultado=1, empresa='13', cuenta='900000000281', centro='17', fecha_contable='2026-10-21', valor_debe='2910.00', valor_haber='2912.00', **kwargs)


def test_marcador_explicito():
    assert evaluar_procedencia([fila(concepto='PRUEBA SINTETICA')])['registros'][0]['estado'] == BLOQUEADO


def test_marcador_observ():
    assert evaluar_procedencia([fila(observ='prueba sintetica')])['registros'][0]['estado'] == BLOQUEADO


def test_ha32_correlacion_no_es_prueba():
    a=fila(concepto='PRUEBA SINTETICA')
    b=fila('HA32'); b['id_host_resultado']=2
    r=evaluar_procedencia([a,b])['registros'][1]
    assert r['estado'] == NO_VERIFICADO and r['motivo']=='CORRELACION_CON_SINTETICO'


def test_sin_evidencia():
    assert evaluar_procedencia([fila()])['registros'][0]['estado'] == NO_VERIFICADO


def test_evidencia_incompleta_no_habilita():
    assert evaluar_procedencia([fila()], {1:{'verificado':True,'origen':'HOST'}})['registros'][0]['estado'] == NO_VERIFICADO


def test_evidencia_completa():
    r=evaluar_procedencia([fila()], {1:{'verificado':True,'origen':'HOST','integridad_verificada':True}})['registros'][0]
    assert r['estado'] == VERIFICADO and r['certificable_por_procedencia']


def test_marcador_prevalece_sobre_evidencia():
    r=evaluar_procedencia([fila(concepto='PRUEBA SINTETICA')], {1:{'verificado':True,'origen':'HOST','integridad_verificada':True}})['registros'][0]
    assert r['estado'] == BLOQUEADO


def test_diferente_importe_no_correlacion():
    a=fila(concepto='PRUEBA SINTETICA')
    b=fila('HA32'); b.update(id_host_resultado=2, valor_debe='9999')
    assert evaluar_procedencia([a,b])['registros'][1]['motivo']=='EVIDENCIA_INSUFICIENTE'
