from pathlib import Path

def test_recepcion_programa_ingesta_individual_antes_de_jornada():
    s = Path("backend/app/api/archivos.py").read_text(encoding="utf-8")
    assert "background_tasks.add_task(procesar_archivo_recibido_f1, id_jornada_bloqueada, id_archivo)" in s
    assert s.index("background_tasks.add_task(procesar_archivo_recibido_f1") < s.index("background_tasks.add_task(procesar_jornada_si_lista")

def test_worker_protege_archivo_vigente_y_ceros():
    s = Path("backend/app/services/procesamiento_individual_f1.py").read_text(encoding="utf-8")
    assert "a.id_archivo = i.id_archivo" in s
    assert "pg_try_advisory_lock" in s
    assert "total <= 0" in s
    assert "con_confirmacion_sin_movimientos" in s
    assert 'jornada_estado == "COMPLETADA"' in s

def test_no_procesamiento_manual_en_ux():
    s = Path("frontend/index.html").read_text(encoding="utf-8")
    assert "Ingesta Fase 1 en curso" in s
    assert "Volver a subir" in s
    assert 'class="btn btnProcesarArchivo"' not in s
