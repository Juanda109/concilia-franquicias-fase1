from decimal import Decimal

import pytest

from app.services.fase2.formulas_redeban_inc60 import proyectar


def muestra():
    return [{
        "NIVEL": "1.1.1.10.102",
        "ES_CONTROL": False,
        "numero_linea": 8,
        "DEBITO_VALOR": Decimal("100"),
        "CREDITO_VALOR": Decimal("20"),
        "DEBITO_COMISION_INTERCAMBIO": Decimal("10"),
        "CREDITO_COMISION_INTERCAMBIO": Decimal("3"),
        "DEBITO_COMISION_ADMINISTRATIVA": Decimal("5"),
        "CREDITO_COMISION_ADMINISTRATIVA": Decimal("2"),
    }]


@pytest.mark.parametrize(
    "tipo,esperado",
    [
        ("A", "80"),
        ("B", "7"),
        ("C", "3"),
    ],
)
def test_calculo_por_tipo(tipo, esperado):
    r = proyectar(muestra(), "1.1.1.10.102", tipo)

    assert r["estado"] == "CALCULO_DIAGNOSTICO"
    assert Decimal(r["neto_diagnostico"]) == Decimal(esperado)
    assert r["certificado"] is False
    assert r["diferencia_certificada"] is None


def test_codigo_inexistente():
    r = proyectar(muestra(), "9.9.9", "A")

    assert r["estado"] == "OPERANDOS_NO_RESUELTOS"
    assert r["neto_diagnostico"] is None


def test_codigo_duplicado():
    filas = muestra()
    filas.append(dict(filas[0]))

    r = proyectar(filas, "1.1.1.10.102", "A")

    assert r["estado"] == "OPERANDOS_NO_RESUELTOS"
    assert r["debito"]["estado"] == "NIVEL_DUPLICADO"
    assert r["neto_diagnostico"] is None


def test_valor_ausente():
    filas = muestra()
    filas[0]["DEBITO_VALOR"] = None

    r = proyectar(filas, "1.1.1.10.102", "A")

    assert r["estado"] == "VALOR_AUSENTE"
    assert r["neto_diagnostico"] is None


def test_tipo_invalido():
    with pytest.raises(ValueError):
        proyectar(muestra(), "1.1.1.10.102", "D")


def test_excluye_controles():
    filas = muestra()
    filas[0]["ES_CONTROL"] = True

    r = proyectar(filas, "1.1.1.10.102", "A")

    assert r["estado"] == "OPERANDOS_NO_RESUELTOS"
    assert r["neto_diagnostico"] is None
