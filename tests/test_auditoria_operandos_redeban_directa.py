from app.services.fase2.auditoria_operandos_redeban import auditar


def fila(codigo='1.1', categoria='A'):
    return dict(cuenta_contable='299095240', estado='OPERANDOS_NO_RESUELTOS',
                fila_excel=42, codigo_operacion=codigo, categoria=categoria)


def pmd(nivel='1.1', **kwargs):
    return dict(NIVEL=nivel, ES_CONTROL=False, numero_linea=3, **kwargs)


def test_sin_coincidencia():
    r = auditar([fila()], ['299095240'], [pmd('2.2')])
    assert r['cuentas']['299095240']['causas'] == {
        'DEBITO:SIN_COINCIDENCIA|CREDITO:SIN_COINCIDENCIA': 1}


def test_duplicados():
    datos = [pmd(DEBITO_VALOR='10', CREDITO_VALOR='0'),
             pmd(DEBITO_VALOR='20', CREDITO_VALOR='0')]
    r = auditar([fila()], ['299095240'], datos)
    assert 'NIVEL_DUPLICADO' in r['pendientes_detalle'][0]['causa']


def test_valor_ausente():
    r = auditar([fila()], ['299095240'], [pmd(DEBITO_VALOR=None, CREDITO_VALOR='0')])
    assert r['pendientes_detalle'][0]['causa'] == 'DEBITO:VALOR_AUSENTE'


def test_sin_diagnostico_si_no_hay_pmd():
    r = auditar([fila()], ['299095240'])
    assert r['pendientes_detalle'][0]['causa'] == 'SIN_DIAGNOSTICO'


def test_cuenta_fuera_alcance():
    r = auditar([fila()], ['196095001828'], [])
    assert not r['cuentas']
