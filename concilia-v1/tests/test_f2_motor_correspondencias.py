import json
import pytest
from app.services.fase2.motor_correspondencias import evaluate, load_rules

H = dict(id_host_resultado=1, id_archivo=1136, tx_host='HA22', cuenta='123', centro='17', concepto='REAL', fecha_contable='2026-10-21', valor_debe='100.00', origen_verificado=True)
F = dict(id_canje_detalle=2, id_archivo=1253, tipo_archivo='CAET', cuenta='017-PRUEBA', fecha_contable='2026-10-21', vl_total='100.00')
R = dict(id_regla='R-01', estado_regla='APROBADA', fuente_host='HA22', cuenta_host='123', centro_host='17', concepto_host='REAL', tipo_insumo='CAET', cuenta_franquicia='017-PRUEBA', campo_host='valor_debe', campo_franquicia='vl_total', factor_signo='1', tolerancia='0')

def test_empty_matrix(): assert evaluate(H,F,[])['estado']=='SIN_MAPEO'
def test_proposal_not_applied(): assert evaluate(H,F,[dict(R,estado_regla='PROPUESTA')])['estado']=='SIN_MAPEO'
def test_synthetic_blocked(): assert evaluate(dict(H,concepto='PRUEBA SINTETICA'),F,[R])['estado']=='BLOQUEADO_SINTETICO'
def test_unverified_origin_blocked(): assert evaluate(dict(H,origen_verificado=False),F,[R])['estado']=='ORIGEN_NO_VERIFICADO'
def test_match(): assert evaluate(H,F,[R])['estado']=='COINCIDE'
def test_difference(): assert evaluate(H,dict(F,vl_total='99.99'),[R])['estado']=='DIFERENCIA'
def test_tolerance(): assert evaluate(H,dict(F,vl_total='99.99'),[dict(R,tolerancia='0.01')])['estado']=='COINCIDE'
def test_ambiguous(): assert evaluate(H,F,[R,dict(R,id_regla='R-02')])['estado']=='MAPEO_AMBIGUO'
def test_missing_is_not_zero(): assert evaluate(dict(H,valor_debe=None),F,[R])['estado']=='DATOS_INSUFICIENTES'
def test_wrong_source(): assert evaluate(dict(H,tx_host='HA26'),F,[R])['estado']=='SIN_MAPEO'
def test_wrong_date(): assert evaluate(H,dict(F,fecha_contable='2026-10-22'),[R])['estado']=='SIN_MAPEO'
def test_empty_json(tmp_path):
 p=tmp_path/'matrix.json'; p.write_text(json.dumps({'fase':2,'reglas':[]})); assert load_rules(p)==[]
def test_invalid_tolerance(tmp_path):
 p=tmp_path/'matrix.json'; p.write_text(json.dumps({'fase':2,'reglas':[dict(R,tolerancia='-1')]}))
 with pytest.raises(ValueError): load_rules(p)
