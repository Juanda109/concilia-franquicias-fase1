from app.api.reporte_maestro_diagnostico import armar_reporte


def test_no_cruces_ni_certificacion():
    r = armar_reporte((1377, '2026-10-21', 'PENDIENTE'), [], [], [])
    assert r['cruces'] == []
    assert r['indicadores']['conciliados'] == 0
    assert r['certificado'] is False


def test_ceros_provisionales():
    r = armar_reporte((1377, '2026-10-21', 'PENDIENTE'), [], [], [])
    depo = next(i for i in r['insumos'] if i['tipo_insumo'] == 'DEPO')
    assert depo['valor_mostrado'] == '0' and depo['valor_provisional'] is True


def test_preservar_nulos_y_ceros():
    r = armar_reporte((1377, '2026-10-21', 'PENDIENTE'), [], [
        dict(id_archivo=1254, cuenta=None, concepto='A', valor=None, franquicia='CREDIBANCO', correlation_id='a'),
        dict(id_archivo=1254, cuenta='1', concepto='B', valor=0, franquicia='CREDIBANCO', correlation_id='b')], [])
    assert r['resultados_franquicia'][0]['valor'] is None
    assert r['resultados_franquicia'][1]['valor'] == '0'
