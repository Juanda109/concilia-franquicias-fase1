from decimal import Decimal
import pytest
from app.services.fase2.reglas_plantilla_maestra import calcular, InsumoPendiente

def test_total_nacional_internacional():
    r=calcular("PM37-O15",{"M15":"120.25","N15":"30.10"})
    assert r.valor == Decimal("150.35") and not r.certificado

def test_diferencia_no_inventa_signos():
    assert calcular("PM37-P15",{"L15":100,"O15":110}).valor == -10

def test_total_26():
    assert calcular("PM37-O26",{"M26":20,"N26":5}).valor == 25

def test_diferencia_26():
    assert calcular("PM37-P26",{"L26":20,"O26":5}).valor == 15

def test_ajuste_29():
    assert calcular("PM37-M29",{"M28":80,"M26":30}).valor == 50

def test_suma_29():
    assert calcular("PM37-P29",{f"P{i}":1 for i in range(15,27)}).valor == 12

def test_carta_favor():
    etiqueta="     T O T A L E S   A   F A V O R"
    carta=[{"B":etiqueta,"D":"100","E":"7","G":"3"},{"B":"OTRO","D":"999"}]
    assert calcular("PM37-G38",{},carta).valor == 100
    assert calcular("PM37-G39",{},carta).valor == 7
    assert calcular("PM37-G41",{},carta).valor == 3

def test_carta_sin_evidencia():
    with pytest.raises(InsumoPendiente): calcular("PM37-G38",{})

def test_no_convertir_nulos_en_cero():
    with pytest.raises(InsumoPendiente): calcular("PM37-O15",{"M15":None,"N15":0})

def test_suma_f42():
    assert calcular("PM37-F42",{f"F{i}":1 for i in range(6,42)}).valor == 36

def test_regla_desconocida():
    with pytest.raises(KeyError): calcular("PM37-ARBITRARIA",{})
