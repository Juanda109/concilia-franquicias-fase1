from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_reemplazo_con_bloqueo_y_auditoria():
    code = (ROOT / "backend/app/api/archivos.py").read_text(encoding="utf-8")
    assert 'reemplazo_recibido' in code
    assert 'ARCHIVO_RECIBIDO_REEMPLAZADO' in code
    assert 'con_confirmacion_sin_movimientos' in code
    assert 'checksum_anterior' in code
    assert 'detalle persistido' in code

def test_frontend_no_ofrece_procesar_manual():
    code = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    assert 'puedeReemplazar' in code
    assert 'Volver a subir' in code
    assert 'a.puedeProcesar ?' not in code
    assert 'conectarBotonesProcesamiento();' not in code

def test_detalle_no_cae_a_resultado_legado_para_cant():
    code = (ROOT / "backend/app/api/detalle_archivos.py").read_text(encoding="utf-8")
    assert 'INTERPRETADO_NO_PERSISTIDO' in code
    assert code.index('if tipo in ("CAET", "CANT"):') < code.index('tabla = "con_franquicia_resultado"')
