from pathlib import Path

def test_backend_bloquea_procesado_antes_de_guardar():
    s = Path('backend/app/api/archivos.py').read_text(encoding='utf-8')
    assert 'a.estado AS estado_archivo_anterior' in s
    assert 'esperado["estado"] == "PROCESADO"' in s
    assert 'esperado["estado_archivo_anterior"] == "PROCESADO"' in s
    assert s.index('Archivo procesado exitosamente: no se permite volver a subir') < s.index('guardado = guardar_archivo(')

def test_backend_rechaza_estados_incompatibles():
    s = Path('backend/app/api/archivos.py').read_text(encoding='utf-8')
    assert 'esperado["estado_archivo_anterior"] != esperado["estado"]' in s

def test_frontend_no_reemplaza_procesados():
    s = Path('frontend/index.html').read_text(encoding='utf-8')
    assert "estado === 'RECIBIDO'" in s
    assert "String(archivo?.estado ?? '').toUpperCase() === 'RECIBIDO'" in s
    assert 'Volver a subir' in s
    assert 'class="btn btnProcesarArchivo"' not in s
