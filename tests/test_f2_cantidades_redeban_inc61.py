from decimal import Decimal

import pytest

from app.services.fase2.cantidades_redeban_inc61 import (
    comparar_cantidad,
)


def catalogo(db, cr):
    return {
        "fila_excel": 272,
        "codigo_operacion": "2.1.1.17.2114",
        "cantidad_debito_formula": db,
        "cantidad_credito_formula": cr,
    }


def pmd(db="550", cr="0"):
    return {
        "DEBITO_CANTIDAD": Decimal(db),
        "CREDITO_CANTIDAD": Decimal(cr),
    }


def test_cantidad_fija_diferente():
    r = comparar_cantidad(
        catalogo(352, 0), pmd(), "DEBITO"
    )

    assert r["estado"] == "CANTIDAD_FIJA_DIFERENTE"
    assert r["cantidad_plantilla"] == "352"
    assert r["cantidad_pmd"] == "550"
    assert r["certificado"] is False


def test_cantidad_fija_coincidente():
    r = comparar_cantidad(
        catalogo(352, 0), pmd(), "CREDITO"
    )

    assert r["estado"] == "CANTIDAD_FIJA_COINCIDENTE"


def test_formula_pmd():
    r = comparar_cantidad(
        catalogo(
            "=IFERROR(VLOOKUP(F272,PMD!$C:$N,2,0),0)",
            "=IFERROR(VLOOKUP(F272,PMD!$C:$N,7,0),0)",
        ),
        pmd(),
        "DEBITO",
    )

    assert r["estado"] == "CANTIDAD_PMD"
    assert r["cantidad_plantilla"] == "550"


def test_formula_indice_incorrecto():
    r = comparar_cantidad(
        catalogo(
            "=VLOOKUP(F272,PMD!$C:$N,3,0)",
            None,
        ),
        pmd(),
        "DEBITO",
    )

    assert r["estado"] == "CANTIDAD_FORMULA_NO_RECONOCIDA"


def test_cantidad_vacia():
    r = comparar_cantidad(
        catalogo(None, None), pmd(), "DEBITO"
    )

    assert r["estado"] == "CANTIDAD_VACIA"


def test_float_no_exacto():
    r = comparar_cantidad(
        catalogo(352.0, 0), pmd(), "DEBITO"
    )

    assert r["estado"] == "CANTIDAD_FIJA_NO_EXACTA"


def test_pmd_ausente_en_fijo():
    r = comparar_cantidad(
        catalogo(352, 0),
        {"DEBITO_CANTIDAD": None},
        "DEBITO",
    )

    assert r["estado"] == "CANTIDAD_PMD_AUSENTE"


def test_lado_invalido():
    with pytest.raises(ValueError):
        comparar_cantidad(
            catalogo(352, 0), pmd(), "TOTAL"
        )


def test_formula_pmd_ausente():
    r = comparar_cantidad(
        catalogo(
            "=IFERROR(VLOOKUP(F272,PMD!$C:$N,2,0),0)",
            None,
        ),
        {"DEBITO_CANTIDAD": None},
        "DEBITO",
    )

    assert r["estado"] == "CANTIDAD_PMD_AUSENTE"
    assert r["cantidad_plantilla"] is None
    assert r["certificado"] is False


def test_formula_indice_credito_incorrecto():
    r = comparar_cantidad(
        catalogo(
            None,
            "=IFERROR(VLOOKUP(F272,PMD!$C:$N,8,0),0)",
        ),
        pmd(),
        "CREDITO",
    )

    assert r["estado"] == "CANTIDAD_FORMULA_NO_RECONOCIDA"
    assert r["certificado"] is False


@pytest.mark.parametrize("formula", [
    "=IFERROR(VLOOKUP(F272,PMD!$C:$N,2,0),0)*10",
    "=IFERROR(VLOOKUP(F272,PMD!$C:$N,2,0),0)+100",
    "=IFERROR(VLOOKUP(F999,PMD!$C:$N,2,0),0)",
    "=IFERROR(VLOOKUP(F272,PMD!$C:$N,2,0),1)",
])
def test_formula_rechaza_operaciones_adicionales(formula):
    r = comparar_cantidad(
        catalogo(formula, None),
        pmd(),
        "DEBITO",
    )

    assert r["estado"] == "CANTIDAD_FORMULA_NO_RECONOCIDA"
    assert r["cantidad_plantilla"] is None
    assert r["certificado"] is False


def test_formula_valida_con_referencia_absoluta():
    r = comparar_cantidad(
        catalogo(
            "=+IFERROR(VLOOKUP($F272,PMD!$C:$N,2,0),0)",
            None,
        ),
        pmd(),
        "DEBITO",
    )

    assert r["estado"] == "CANTIDAD_PMD"
    assert r["cantidad_plantilla"] == "550"
