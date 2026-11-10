import os
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers.vss import VSSParser, _amount


def crear_vss(tmp_path, contenido):
    archivo = tmp_path / "vss_prueba.txt"
    archivo.write_text(contenido, encoding="utf-8")
    return archivo


def test_vss_archivo_real():
    ruta = os.environ.get("VSS_SAMPLE")

    if not ruta or not Path(ruta).is_file():
        pytest.skip("Muestra VSS no disponible")

    resultado = VSSParser().parse(Path(ruta))

    assert resultado.errors == []
    assert len(resultado.records) == 46

    reportes = {
        r["REPORTE"] for r in resultado.records
    }

    assert reportes == {
        "VSS-110",
        "VSS-115",
        "VSS-120"
    }

    assert sum(r["ES_CONTROL"] for r in resultado.records) == 32

    assert any(
        "NET SETTLEMENT AMOUNT" in r["CONCEPTO"].upper()
        for r in resultado.records
    )


@pytest.mark.parametrize(
    "token,valor,signo",
    [
        ("1,234.56CR", Decimal("1234.56"), "CR"),
        ("1,234.56DB", Decimal("1234.56"), "DB"),
        ("-500.00", Decimal("-500.00"), None),
        ("0.00", Decimal("0.00"), None),
    ]
)
def test_vss_importes(token, valor, signo):
    obtenido, indicador = _amount(token)

    assert obtenido == valor
    assert indicador == signo


def test_vss_archivo_vacio(tmp_path):
    archivo = crear_vss(tmp_path, "")

    resultado = VSSParser().parse(archivo)

    assert len(resultado.records) == 0
    assert resultado.errors[0].codigo == "SIN_REGISTROS"


def test_vss_sin_reportes(tmp_path):
    archivo = crear_vss(
        tmp_path,
        "TEXTO SIN ESTRUCTURA VSS\n"
    )

    resultado = VSSParser().parse(archivo)

    assert len(resultado.records) == 0
    assert resultado.errors[0].codigo == "SIN_REGISTROS"


def test_vss_conserva_signo_cr_db():
    valor_cr, signo_cr = _amount("1500.00CR")
    valor_db, signo_db = _amount("1500.00DB")

    assert valor_cr == valor_db
    assert signo_cr == "CR"
    assert signo_db == "DB"
