import pytest

from app.services.fase2.referencias_redeban_inc62 import (
    evaluar_referencia,
)


def fila(formula):
    return {
        "fila_excel": 8,
        "codigo_operacion": "1.1.1.10.102",
        "cuenta_contable": "196095001828",
        "referencia_contable_formula": formula,
    }


@pytest.mark.parametrize(
    "formula,esperado",
    [
        ("=+$M$1", "010926"),
        ("=+$M$2", "240926"),
        ("=(+$M$2)", "240926"),
        ('=+"75"&$M$2', "75240926"),
        ('=+"71"&$M$2', "71240926"),
        ('=+"67"&$M$2', "67240926"),
    ],
)
def test_formulas_reconocidas(formula, esperado):
    r = evaluar_referencia(
        fila(formula), "010926", "240926", "VERSION_PRUEBA"
    )

    assert r["estado"] == "REFERENCIA_FORMULA_RECONOCIDA"
    assert r["referencia_diagnostica"] == esperado
    assert r["certificado"] is False


def test_literal_texto():
    r = evaluar_referencia(
        fila("010925"), "010926", "240926", "VERSION_PRUEBA"
    )

    assert r["estado"] == "REFERENCIA_LITERAL_TEXTO"
    assert r["referencia_diagnostica"] == "010925"


def test_literal_numerico():
    r = evaluar_referencia(
        fila(230926), "010926", "240926", "VERSION_PRUEBA"
    )

    assert r["estado"] == "REFERENCIA_LITERAL_NUMERICA"
    assert r["referencia_diagnostica"] == "230926"
    assert r["tipo_original"] == "int"


@pytest.mark.parametrize(
    "formula",
    [
        '=+"99"&$M$2',
        "=+$M$3",
        "=+$M$2+100",
        "=H8",
    ],
)
def test_formulas_desconocidas(formula):
    r = evaluar_referencia(
        fila(formula), "010926", "240926", "VERSION_PRUEBA"
    )

    assert r["estado"] == "REFERENCIA_FORMULA_DESCONOCIDA"
    assert r["referencia_diagnostica"] is None


def test_parametro_invalido():
    r = evaluar_referencia(
        fila("=+$M$1"), None, "240926", "VERSION_PRUEBA"
    )

    assert r["estado"] == "REFERENCIA_PARAMETRO_INVALIDO"


def test_version_obligatoria():
    with pytest.raises(ValueError):
        evaluar_referencia(
            fila("=+$M$2"), "010926", "240926", None
        )


def test_conserva_trazabilidad():
    r = evaluar_referencia(
        fila("=+$M$2"), "010926", "240926", "VERSION_PRUEBA"
    )

    assert r["fila_excel"] == 8
    assert r["codigo_operacion"] == "1.1.1.10.102"
    assert r["cuenta_contable"] == "196095001828"
    assert r["version_catalogo"] == "VERSION_PRUEBA"
    assert r["certificado"] is False
