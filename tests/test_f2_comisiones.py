from app.services.fase2.diagnostico_comisiones_f2 import evaluar

def base(**kwargs):
    row = dict(tx='02', tipo='DEBITO', espacios='ELECTRONICO', bin_dest='404280',
               vl_total='10000', vl_interc='9000', comision_op_exitosas='7450',
               tii_recibida_emisor_visa_op_rever_ventas=None,
               cuentas_comisiones='017-COMISIONES EXIT. TARJETA DEBITO ONLINE', cuenta_880=None)
    row.update(kwargs)
    return row

def test_debito():
    r=evaluar(base())
    assert r['estado_comision']=='COINCIDE' and r['estado_cuenta_comision']=='COINCIDE'

def test_bin_excluido():
    r=evaluar(base(bin_dest='439467', comision_op_exitosas=None, cuentas_comisiones=None))
    assert r['estado_comision']=='COINCIDE'

def test_credito_tii():
    r=evaluar(base(tx='26', tipo='CREDITO', comision_op_exitosas=None, cuentas_comisiones='017-TII RECIBIDA EMISOR VISA OP REVER VENTAS', tii_recibida_emisor_visa_op_rever_ventas='1000'))
    assert r['estado_tii']=='COINCIDE'

def test_regalo():
    r=evaluar(base(bin_dest='462550', cuenta_880='017-CANJE RECIBIDO TARJETA DEBITO REGALO'))
    assert r['estado_cuenta_880']=='COINCIDE'

def test_diferencia():
    assert evaluar(base(comision_op_exitosas='0'))['estado_comision']=='DIFIERE'
