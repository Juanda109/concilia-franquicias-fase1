from app.services.fase2.diagnostico_completo_canje import classify, analyze

def test_clasifica_debito():
    cuenta, regla, cobertura = classify(dict(tx='02',tipo='DEBITO',canal='ELECTRONICO',cod_error='00',bin_dest='404280',mot_cob=''))
    assert regla == 'F2-CANJE-CUENTA-001'
    assert cobertura == 'EVALUADA'

def test_prioridad_representacion():
    cuenta, regla, cobertura = classify(dict(tx='36',tipo='CREDITO',canal='MANUAL',cod_error='00',bin_dest='404280',mot_cob=''))
    assert regla == 'F2-CANJE-CUENTA-009'

def test_sin_regla_no_es_coincidencia():
    rows, counts, _ = analyze([dict(id_archivo=1,linea_origen=1,tx='98',tipo='CREDITO',canal='MANUAL',cod_error='00',bin_dest='404280',mot_cob='',cuenta_historica='')])
    assert counts['SIN_REGLA_F2'] == 1

def test_incompleto_no_es_diferencia():
    rows, counts, _ = analyze([dict(id_archivo=1,linea_origen=1,tx=None,tipo='CREDITO',cod_error='00',cuenta_historica='X')])
    assert counts['NO_EVALUADA'] == 1

def test_error_no_aplicable():
    assert classify(dict(tx='02',tipo='DEBITO',cod_error='99'))[1] == 'F2-COD-ERROR'
