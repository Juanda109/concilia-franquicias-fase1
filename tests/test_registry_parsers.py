import pytest

from app.ingestion.registry import obtener_parser


@pytest.mark.parametrize(
    "tipo",
    [
        "HA22",
        "HA26",
        "HA32",
        "PMD",
        "MEP",
        "VSS",
        "CAET",
        "CANT",
        "DEPO",
        "CARTA_COMPENSACION",
    ]
)
def test_parser_registrado(tipo):
    parser = obtener_parser(tipo)

    assert parser.tipo_insumo == tipo
    assert callable(parser.parse)


@pytest.mark.parametrize(
    "tipo",
    ["CAIT"]
)
def test_parser_no_disponible(tipo):
    with pytest.raises(ValueError):
        obtener_parser(tipo)


def test_normalizacion_nombre_parser():
    parser = obtener_parser(" ha22 ")

    assert parser.tipo_insumo == "HA22"
