import importlib.util
from pathlib import Path
import pytest
p=Path(__file__).resolve().parents[1]/'backend'/'app'/'services'/'fase2'/'diagnostico_movimientos.py'
spec=importlib.util.spec_from_file_location('diag_f2',p)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
def test_regla_debito():
    assert m.classify(dict(tx='02',tipo='DEBITO',canal='ELECTRONICO',cod_error='00'))[1]=='F2-CANJE-DB-02-06'
def test_representacion():
    assert m.classify(dict(tx='36',tipo='',canal='',cod_error='00'))[1]=='F2-REP-36'
def test_no_evaluada_no_es_diferencia():
    rows,c,_=m.analyze([dict(id_archivo=1,linea_origen=2,tx='44',cuenta_historica='X')])
    assert rows[0]['resultado_comparacion']=='NO_EVALUADA'
def test_datos_decimales():
    rows,c,s=m.analyze([dict(id_archivo=1,linea_origen=2,tx='44',cuenta_historica='X',valor='0.10',intercambio='0.20'),dict(id_archivo=1,linea_origen=3,tx='44',cuenta_historica='X',valor='0.20',intercambio='0.10')])
    assert str(s['X']['valor'])=='0.30'
def test_columnas_obligatorias():
    with pytest.raises(ValueError): m.select_columns({'id_archivo'})
def test_columna_opcional():
    assert m.select_columns({'id_archivo','linea_origen'})['comision'] is None
def test_no_sobrescribe_salida(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_NAME','concilia_test')
    with pytest.raises(FileExistsError): m.run([1253,1254],tmp_path)
