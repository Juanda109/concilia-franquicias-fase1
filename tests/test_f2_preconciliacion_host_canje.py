from decimal import Decimal
from app.services.fase2.preconciliacion_host_canje import es_sintetico, consolidar_host, consolidar_canje

def test_sintetico():
    assert es_sintetico('prueba sintetica')
    assert not es_sintetico(None)

def test_host_separado():
    base=dict(tx_host='HA22',cuenta='123',centro='17',concepto='PRUEBA SINTETICA',valor_debe=2,valor_haber=4,valor_normalizado=-2)
    grupos=consolidar_host([dict(base,id_archivo=1136),dict(base,id_archivo=1141)])
    assert len(grupos)==2
    assert all(g['estado']=='DATOS_SINTETICOS' for g in grupos)

def test_canje_decimal():
    rows=[dict(id_archivo=1253,cuenta='X',vl_total='0.1',vl_interc='0.1'),dict(id_archivo=1253,cuenta='X',vl_total='0.2',vl_interc='0.2')]
    g=consolidar_canje(rows)
    assert g[0]['valor']==Decimal('0.3') and g[0]['estado']=='SIN_MAPEO'

def test_no_inventa_mapeo():
    r=consolidar_host([dict(id_archivo=1136,tx_host='HA22',cuenta='123',centro='17',concepto='REAL',valor_debe=1,valor_haber=1,valor_normalizado=0)])
    assert r[0]['estado']=='SIN_MAPEO'
