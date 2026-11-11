import pytest

from app.ingestion.registry import obtener_parser
from app.ingestion.catalogo import INSUMOS_FUNCIONALES


@pytest.mark.parametrize(
    "tipo",
    [
        "HA22",
        "HA26",
        "HA32",
        "PMD",
        "VSS",
        "VISA_SS_INTERNATIONAL",
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
    ["CAIT", "MEP"]
)
def test_parser_no_disponible(tipo):
    with pytest.raises(ValueError):
        obtener_parser(tipo)


def test_normalizacion_nombre_parser():
    parser = obtener_parser(" ha22 ")

    assert parser.tipo_insumo == "HA22"


def test_catalogo_funcional_mvp1_tiene_los_diez_insumos():
    esperados = {
        "HA22", "HA26", "HA32",
        "CAET", "CANT", "DEPO", "CARTA_COMPENSACION",
        "PMD", "VSS", "VISA_SS_INTERNATIONAL",
    }
    assert set(INSUMOS_FUNCIONALES) == esperados
    assert len(INSUMOS_FUNCIONALES) == 10
