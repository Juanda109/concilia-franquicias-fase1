from app.services.fase2.recalculo_comisiones_f2 import calculate, summarize, numeric


def test_comision_aplica():
    r = calculate({'tx': '02', 'bin_dest': '404280'})
    assert r['estado_comision'] == 'CALCULADO' and r['comision_f2'] == '7450'


def test_bin_excluido():
    assert calculate({'tx': '02', 'bin_dest': '439467'})['estado_comision'] == 'NO_APLICA'


def test_bin_ausente():
    assert calculate({'tx': '02'})['estado_comision'] == 'DATOS_INSUFICIENTES'


def test_tii():
    r = calculate({'tx': '26', 'tipo': 'CREDITO', 'vl_total': '1000.50', 'vl_interc': '20.25'})
    assert r['tii_f2'] == '980.25'


def test_tii_nulo():
    assert calculate({'tx': '26', 'tipo': 'CREDITO', 'vl_total': '100'})['estado_tii'] == 'DATOS_INSUFICIENTES'


def test_no_aplica_no_es_cero():
    r = calculate({'tx': '08', 'tipo': 'DEBITO'})
    assert r['comision_f2'] is None and r['tii_f2'] is None


def test_totales():
    _, report = summarize([{'tx': '02', 'bin_dest': '404280'}, {'tx': '02', 'bin_dest': '404280'}, {'tx': '26', 'tipo': 'CREDITO', 'vl_total': '200', 'vl_interc': '50'}])
    assert report['total_comision_f2'] == '14900'
    assert report['total_tii_f2'] == '150'
