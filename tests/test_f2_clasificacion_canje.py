import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.fase2.clasificacion_canje import clasificar_cuenta, clasificar_comision, clasificar_regalo

def test_error_no_clasifica():
    r=clasificar_cuenta(cod_error="01",tipo="CREDITO",canal="ELECTRONICO",tx="36",bin_dest="404280",mot_cob="")
    assert r.cuenta is None and r.motivo=="COD_ERROR_NO_APLICABLE"

def test_representacion():
    r=clasificar_cuenta(cod_error="00",tipo="CREDITO",canal="ELECTRONICO",tx="36",bin_dest="404280",mot_cob="")
    assert r.regla_id=="F2-CANJE-CUENTA-009"

def test_prioridad_tx42():
    r=clasificar_cuenta(cod_error="00",tipo="CREDITO",canal="ELECTRONICO",tx="42",bin_dest="404280",mot_cob="04")
    assert r.regla_id=="F2-CANJE-CUENTA-012"

def test_regalo():
    assert clasificar_regalo(bin_dest="417704",tipo="DEBITO",canal="Manual",tx="06").regla_id=="F2-REGALO-001"

def test_comision():
    assert clasificar_comision(tipo="CREDITO",canal="ELECTRONICO",tx="02",comision=7450,tii=None).regla_id=="F2-COM-002"
