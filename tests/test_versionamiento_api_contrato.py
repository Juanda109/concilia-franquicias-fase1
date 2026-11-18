from pathlib import Path


def test_api_expone_versionamiento_explicito_y_auditable():
    codigo = Path("backend/app/api/archivos.py").read_text(encoding="utf-8")

    assert 'nueva_version: bool = Form(False)' in codigo
    assert 'motivo_version: str | None = Form(None)' in codigo
    assert 'con_insumo_archivo_version' in codigo
    assert "ARCHIVO_VERSION_RECIBIDO" in codigo
    assert 'numero_version' in codigo


def test_migracion_conserva_historial_y_un_solo_vigente():
    sql = Path(
        "sql/migrations/039_VERSIONAMIENTO_ARCHIVOS_INSUMO.sql"
    ).read_text(encoding="utf-8")

    assert "REFERENCES public.con_archivo_carga(id_archivo)" in sql
    assert "REFERENCES public.con_insumo_esperado(id_insumo_esperado)" in sql
    assert "WHERE estado_version = 'VIGENTE'" in sql
    assert "SUSTITUIDA" in sql
    assert "Version inicial conocida" in sql


def test_api_expone_consulta_de_historial_de_versiones():
    codigo = Path("backend/app/api/archivos.py").read_text(encoding="utf-8")
    assert '@router.get("/{id_archivo}/versiones")' in codigo
    assert '"total_versiones"' in codigo
    assert 'v.motivo_version' in codigo
