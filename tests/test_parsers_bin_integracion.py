import pytest

from app.parsers import caet, cant


@pytest.mark.parametrize("modulo", [caet, cant])
def test_clasificacion_bin_compartida(monkeypatch, modulo):
    llamadas = []

    def catalogo_simulado():
        llamadas.append(1)
        return {
            123456: "DEBITO",
            654321: "CREDITO",
        }

    monkeypatch.setattr(
        modulo,
        "cargar_bines_activos",
        catalogo_simulado
    )

    assert modulo._tipo("0001234560000000000") == "DEBITO"
    assert modulo._tipo("0006543210000000000") == "CREDITO"
    assert modulo._tipo("0009999990000000000") == ""

    assert len(llamadas) == 3


@pytest.mark.parametrize("modulo", [caet, cant])
def test_bin_no_numerico(monkeypatch, modulo):
    def catalogo_no_debe_consultarse():
        raise AssertionError(
            "No debe consultar catalogo para BIN invalido"
        )

    monkeypatch.setattr(
        modulo,
        "cargar_bines_activos",
        catalogo_no_debe_consultarse
    )

    assert modulo._tipo("000ABCDEF0000000000") == ""
