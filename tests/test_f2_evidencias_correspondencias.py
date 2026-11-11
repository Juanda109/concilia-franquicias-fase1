import json
from pathlib import Path
import pytest
from app.services.fase2.validacion_evidencias_f2 import validar_evidencias

RUTA = Path(__file__).resolve().parents[1] / "backend/app/services/fase2/matriz_evidencias_credibanco.json"

def test_siete_pendientes():
    r=validar_evidencias(RUTA)
    assert r["total"] == 7 and r["aprobadas"] == 0

def test_candidatas_documentadas():
    assert validar_evidencias(RUTA)["candidatas_documentadas"] == 3

def test_no_activar(tmp_path):
    d=json.loads(RUTA.read_text(encoding="utf-8")); d["reglas"][0]["habilitada"]=True
    p=tmp_path/"m.json";p.write_text(json.dumps(d))
    with pytest.raises(ValueError,match="activar"):validar_evidencias(p)

def test_no_duplicar(tmp_path):
    d=json.loads(RUTA.read_text(encoding="utf-8")); d["reglas"][1]["id_regla"]=d["reglas"][0]["id_regla"]
    p=tmp_path/"m.json";p.write_text(json.dumps(d))
    with pytest.raises(ValueError,match="duplicado"):validar_evidencias(p)

def test_no_candidata_sin_evidencia(tmp_path):
    d=json.loads(RUTA.read_text(encoding="utf-8"));d["reglas"][4]["evidencias"]=[]
    p=tmp_path/"m.json";p.write_text(json.dumps(d))
    with pytest.raises(ValueError,match="evidencia"):validar_evidencias(p)
