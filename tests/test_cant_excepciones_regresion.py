from pathlib import Path
from app.services.normalizacion_credibanco import normalizar_cant, CUENTA_REPRESENTACION
from datetime import date
import pytest


def test_normalizador_no_inventa_regla():
    with pytest.raises(ValueError, match="sin regla"):
        normalizar_cant(registros=[{"CUENTA": "017-ORIGINAL REEMBOLSOS DEBITO",
                                  "numero_linea": 2, "VL_TOTAL": "100",
                                  "TX": "36", "BIN_DEST": "492489"}],
                       fecha_contable=date(2026, 10, 21), id_archivo=1254,
                       correlation_id="test")


def test_migracion_excepciones_tiene_clave_unica():
    sql = Path("sql/migrations/033_CANT_EXCEPCIONES_CUENTAS.sql").read_text()
    assert "UNIQUE(id_archivo,linea_origen)" in sql
