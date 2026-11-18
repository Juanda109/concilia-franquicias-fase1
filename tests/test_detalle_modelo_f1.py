import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_contrato_canje_22_columnas():
    tree = ast.parse((ROOT / "backend/app/services/persistencia_detalle.py").read_text())
    assignment = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CAMPOS_CANJE" for t in n.targets))
    campos = ast.literal_eval(assignment.value)
    assert len(campos) == len(set(campos)) == 22
    assert campos[0] == "tx" and campos[-1] == "cuenta_880"

def test_migracion_contiene_tablas():
    ddl = (ROOT / "sql/migrations/019_DETALLE_CANJE_HOST.sql").read_text().lower()
    for tabla in ("con_canje_detalle", "con_ha22_detalle", "con_ha26_detalle", "con_ha32_detalle", "con_detalle_control"):
        assert f"create table if not exists public.{tabla}" in ddl
    assert "drop table" not in ddl
