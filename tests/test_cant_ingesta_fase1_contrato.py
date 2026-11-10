from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cant_fase1_usa_persistencia_detalle():
    api = (ROOT / "backend/app/api/procesamiento_franquicias.py").read_text()
    assert "detalle = persistir_detalle(id_archivo)" in api
    assert "normalizado = procesar_cant(id_archivo)" not in api


def test_cant_recibido_puede_persistir_detalle():
    codigo = (ROOT / "backend/app/services/persistencia_detalle.py").read_text()
    assert "('CAET','CANT','DEPO'" in codigo
    assert "Procesar CANT con el servicio existente primero" not in codigo


def test_orquestador_no_bloquea_por_excepciones_contables():
    codigo = (ROOT / "backend/app/services/procesamiento_automatico.py").read_text()
    assert "SELECT COUNT(*) FROM con_cant_excepcion_cuenta" not in codigo


def test_ux_fase1_no_solicita_excepciones_contables():
    html = (ROOT / "frontend/index.html").read_text()
    assert "const resumenCant = await apiConcilia" not in html
    assert "btnExcepcionesCant" not in html
