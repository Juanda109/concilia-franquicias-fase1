from decimal import Decimal

from app.parsers.ha32 import HA32Parser, COLUMNAS
from app.ingestion.registry import obtener_parser


def crear_archivo(tmp_path, filas):
    archivo = tmp_path / "ha32_prueba.txt"
    contenido = "|".join(COLUMNAS) + "\n"
    contenido += "\n".join(filas) + "\n"
    archivo.write_text(contenido, encoding="utf-8")
    return archivo


def test_ha32_registrado():
    parser = obtener_parser("HA32")
    assert isinstance(parser, HA32Parser)


def test_ha32_registro_valido(tmp_path):
    fila = (
        "HA32|HADV0030|HADV0120|13.|"
        "196095001828|17.|2026-09-14|"
        ".00|.00|-4849302.78"
    )

    resultado = HA32Parser().parse(
        crear_archivo(tmp_path, [fila])
    )

    assert resultado.errors == []
    assert len(resultado.records) == 1

    registro = resultado.records[0]

    assert registro["NUCTA"] == "196095001828"
    assert registro["FECONT"] == "2026-09-14"
    assert registro["DEBE"] == Decimal("0.00")
    assert registro["HABER"] == Decimal("0.00")
    assert registro["SALDO_INICIAL"] == Decimal("-4849302.78")


def test_ha32_columnas_invalidas(tmp_path):
    resultado = HA32Parser().parse(
        crear_archivo(tmp_path, ["HA32|HADV0030"])
    )

    assert len(resultado.records) == 0
    assert resultado.errors[0].codigo == "COLUMNAS_INVALIDAS"


def test_ha32_origen_invalido(tmp_path):
    fila = (
        "HA22|HADV0030|HADV0120|13.|"
        "196095001828|17.|2026-09-14|"
        ".00|.00|100.00"
    )

    resultado = HA32Parser().parse(
        crear_archivo(tmp_path, [fila])
    )

    assert resultado.errors[0].codigo == "ORIGEN_INVALIDO"


def test_ha32_importe_invalido(tmp_path):
    fila = (
        "HA32|HADV0030|HADV0120|13.|"
        "196095001828|17.|2026-09-14|"
        ".00|.00|NO_NUMERICO"
    )

    resultado = HA32Parser().parse(
        crear_archivo(tmp_path, [fila])
    )

    assert resultado.errors[0].codigo == "VALOR_INVALIDO"


import pytest


@pytest.mark.parametrize(
    "importe",
    ["NaN", "Infinity", "-Infinity"]
)
def test_ha32_rechaza_importes_no_finitos(
    tmp_path, importe
):
    fila = (
        "HA32|HADV0030|HADV0120|13.|"
        "196095001828|17.|2026-09-14|"
        f".00|.00|{importe}"
    )

    resultado = HA32Parser().parse(
        crear_archivo(tmp_path, [fila])
    )

    assert len(resultado.records) == 0
    assert len(resultado.errors) == 1
    assert resultado.errors[0].codigo == "VALOR_INVALIDO"


@pytest.mark.parametrize(
    "fecha",
    ["2026-02-30", "2026-13-01", "FECHA_INVALIDA", ""]
)
def test_ha32_fecha_invalida(tmp_path, fecha):
    fila = (
        "HA32|HADV0030|HADV0120|13.|"
        "196095001828|17.|"
        f"{fecha}|.00|.00|100.00"
    )

    resultado = HA32Parser().parse(
        crear_archivo(tmp_path, [fila])
    )

    assert len(resultado.records) == 0
    assert len(resultado.errors) == 1
    assert resultado.errors[0].codigo == "VALOR_INVALIDO"


def test_ha32_encabezado_invalido(tmp_path):
    archivo = tmp_path / "encabezado_invalido.txt"
    archivo.write_text(
        "TX_ORIGEN|NUCTA|DEBE\n",
        encoding="utf-8"
    )

    resultado = HA32Parser().parse(archivo)

    assert len(resultado.records) == 0
    assert resultado.errors[0].codigo == "HEADER_INVALIDO"


def test_ha32_conserva_identificadores(tmp_path):
    fila = (
        "HA32|HADV0030|HADV0120|13.|"
        "00196095001828|17.|2026-09-14|"
        ".00|.00|100.00"
    )

    resultado = HA32Parser().parse(
        crear_archivo(tmp_path, [fila])
    )

    assert resultado.errors == []

    registro = resultado.records[0]

    assert registro["EMPRESA"] == "13."
    assert registro["NUCTA"] == "00196095001828"
    assert registro["CEDESTIN"] == "17."
