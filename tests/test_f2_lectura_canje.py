from decimal import Decimal
import pytest
from app.services.fase2.lectura_canje import transformar_fila, consultar_y_agrupar_canje, CAMPOS


def fila(**changes):
    f = dict(id_archivo=1254, linea_origen=221, tipo_archivo='CANT', tx='36',
             bin_dest='404280', tipo='CREDITO', espacios='ELECTRONICO',
             mot_cob='', cod_error='00', vl_total=Decimal('1850000.00'),
             vl_interc=Decimal('10.00'), comision_op_exitosas=None,
             tii_recibida_emisor_visa_op_rever_ventas=None)
    f.update(changes)
    return f


def test_reclasifica_sin_usar_cuenta_legacy():
    x = fila(cuenta='LEGACY_NO_USAR')
    partidas, audit = transformar_fila(x)
    assert partidas[0]['cuenta'] == '017-REPRESENTACION  VENTA NAL (CENTRO 730)'
    assert audit['regla_cuenta'] == 'F2-CANJE-CUENTA-009'


def test_error_de_clasificacion_queda_sin_cuenta():
    partidas, audit = transformar_fila(fila(cod_error='03'))
    assert partidas[0]['cuenta'] == ''
    assert audit['motivo_cuenta'] == 'COD_ERROR_NO_APLICABLE'


def test_comision_no_duplica_valor_total():
    partidas, _ = transformar_fila(fila(tx='02', comision_op_exitosas=Decimal('7450')))
    assert len(partidas) == 2
    assert partidas[1]['vl_total'] is None
    assert partidas[1]['comision_op_exitosas'] == Decimal('7450')


class Cursor:
    def __init__(self, datos, estado=('CANT','PROCESADO','PROCESADO')):
        self.datos, self.estado, self.step = datos, estado, 0
        self.sql = []
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        if params is not None: assert params == (1254,)
        if sql.startswith('SELECT'): self.step += 1
    def fetchone(self):
        if self.step == 1: return self.estado
        if self.step == 2: return (len(self.datos),)
        raise AssertionError('Unexpected fetchone')
    def fetchall(self): return [tuple(x[c.split('.')[-1]] for c in CAMPOS) for x in self.datos]

class Conn:
    def __init__(self, cursor): self.c = cursor
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def cursor(self): return self.c


def test_consulta_readonly_y_agrega():
    c = Cursor([fila()])
    r = consultar_y_agrupar_canje(1254, lambda: Conn(c))
    assert r['filas_fuente'] == 1
    assert r['resultado']['cantidad_agrupada'] == 1
    assert all(not sql.lstrip().upper().startswith(('UPDATE','INSERT','DELETE','ALTER')) for sql,_ in c.sql)
    assert c.sql[0][0] == 'SET TRANSACTION READ ONLY'


def test_bloquea_no_procesado():
    c = Cursor([fila()], ('CANT','RECIBIDO','RECIBIDO'))
    with pytest.raises(ValueError, match='PROCESADOS'):
        consultar_y_agrupar_canje(1254, lambda: Conn(c))


def test_rechaza_limite():
    c = Cursor([fila(), fila(linea_origen=222)])
    with pytest.raises(ValueError, match='limite seguro'):
        consultar_y_agrupar_canje(1254, lambda: Conn(c), limite=1)


def test_valida_id_archivo():
    with pytest.raises(ValueError, match='id_archivo'):
        consultar_y_agrupar_canje(True, lambda: None)
