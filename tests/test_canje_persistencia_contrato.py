from pathlib import Path
from app.services.persistencia_detalle import CAMPOS_CANJE, NUMERICOS, MAPEO_CANJE


def test_22_columnas_y_mapeo():
    assert len(CAMPOS_CANJE) == 22
    assert len(set(CAMPOS_CANJE)) == 22
    assert MAPEO_CANJE["cuentas_comisiones"] == "CUENTAS_COMISIONES"
    assert {"vl_total", "vl_descue", "vl_interc"} <= NUMERICOS


def test_ddl_monetario():
    sql = Path("sql/migrations/019_DETALLE_CANJE_HOST.sql").read_text(encoding="utf-8-sig").lower()
    assert "vl_total numeric(24,4)" in sql
    assert "vl_descue numeric(24,4)" in sql
    assert "unique (id_archivo, linea_origen)" in sql
