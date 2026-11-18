import pytest
from app.services.fase2.integracion_depo_inc56i import seleccionar_sumatorias_host, consultar_depo_jornada


def test_fuente_host_seleccionada_sin_duplicacion():
    filas = [dict(fuente_host=f, cuenta='196095001838', naturaleza='D', importe_contable='10')
             for f in ('HA22','HA26','HA32')]
    r = seleccionar_sumatorias_host(filas, 'HA22')
    assert len(r['sumatorias_host_seleccionadas']) == 1
    assert r['sumatorias_host_seleccionadas'][0]['importe_contable'] == '10'
    assert r['certificado_monetario'] is False


def test_rechaza_fuente_no_autorizada_y_duplicados():
    with pytest.raises(ValueError):
        seleccionar_sumatorias_host([], 'TODAS')
    fila = dict(fuente_host='HA22', cuenta='196095001838', naturaleza='D', importe_contable='10')
    with pytest.raises(ValueError):
        seleccionar_sumatorias_host([fila, fila], 'HA22')


def test_consulta_con_fuente_sin_archivo_no_inventa_valores():
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def execute(self,*args): pass
        def fetchall(self): return []
    class Conn:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def cursor(self): return Cursor()
    r = consultar_depo_jornada(1377, lambda: Conn(), fuente_host='HA32')
    assert r['fuente_host_seleccionada'] == 'HA32'
    assert r['sumatorias_host_seleccionadas'] == []
    assert r['certificado_monetario'] is False
