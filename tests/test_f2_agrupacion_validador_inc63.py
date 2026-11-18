from decimal import Decimal

import pytest

from app.services.fase2.agrupacion_validador_inc63 import (
    agrupar_estructura,
    decimal_exacto,
    normalizar_nivel,
)


def fila(numero, nivel, debito, credito, neto):
    return {
        "fila_excel": numero,
        "codigo_operacion": f"COD-{numero}",
        "nivel_1": nivel,
        "debito": debito,
        "credito": credito,
        "neto": neto,
    }


def test_agrupacion_por_nivel():
    registros = [
        fila(4, "1.1", "100", "-20", "80"),
        fila(5, "1.1", "50", "-10", "40"),
        fila(6, "2.1", "30", "-5", "25"),
    ]

    r = agrupar_estructura(registros, "VERSION_PRUEBA")

    niveles = {f["nivel"]: f for f in r["niveles"]}

    assert r["cantidad_niveles"] == 2

    assert Decimal(
        niveles["1.1"]["debito_estructura_actual"]
    ) == Decimal("150")

    assert Decimal(
        niveles["1.1"]["credito_estructura_actual"]
    ) == Decimal("-30")

    assert Decimal(
        niveles["1.1"]["neto_estructura_actual"]
    ) == Decimal("120")

    assert niveles["1.1"]["cantidad_filas"] == 2
    assert niveles["1.1"]["filas_origen"] == [4, 5]
    assert r["certificado"] is False


def test_excluye_fuera_de_rango():
    registros = [
        fila(3, "1.1", 100, 0, 100),
        fila(4, "1.1", 20, 0, 20),
        fila(3245, "1.1", 30, 0, 30),
        fila(3246, "1.1", 500, 0, 500),
    ]

    r = agrupar_estructura(registros, "VERSION_PRUEBA")

    nivel = r["niveles"][0]

    assert nivel["filas_origen"] == [4, 3245]
    assert Decimal(
        nivel["neto_estructura_actual"]
    ) == Decimal("50")


def test_conserva_sin_nivel():
    registros = [
        fila(1618, None, 0, 0, 0),
        fila(1619, "", 0, 0, 0),
        fila(2665, "   ", 0, 0, 0),
        fila(2666, None, 0, 0, 0),
    ]

    r = agrupar_estructura(registros, "VERSION_PRUEBA")

    assert r["cantidad_sin_nivel"] == 4
    assert r["cantidad_niveles"] == 0

    assert [
        f["fila_excel"] for f in r["sin_nivel"]
    ] == [1618, 1619, 2665, 2666]

    assert all(
        f["certificado"] is False
        for f in r["sin_nivel"]
    )


def test_decimal_exacto():
    assert decimal_exacto("0.01") == Decimal("0.01")
    assert decimal_exacto(None) == Decimal("0")


@pytest.mark.parametrize(
    "valor",
    [True, False, "NaN", "Infinity", "abc"],
)
def test_importe_invalido(valor):
    with pytest.raises(ValueError):
        decimal_exacto(valor)


def test_normalizar_nivel():
    assert normalizar_nivel(" 1.1 ") == "1.1"
    assert normalizar_nivel(None) is None
    assert normalizar_nivel("   ") is None


def test_version_obligatoria():
    with pytest.raises(ValueError):
        agrupar_estructura([], None)


def test_fila_excel_invalida():
    with pytest.raises(ValueError):
        agrupar_estructura(
            [fila(True, "1.1", 1, 0, 1)],
            "VERSION_PRUEBA",
        )


def test_conserva_version():
    r = agrupar_estructura(
        [fila(8, "1.1", 100, -20, 80)],
        "VERSION_PRUEBA",
    )

    assert r["version_catalogo"] == "VERSION_PRUEBA"
    assert r["niveles"][0]["version_catalogo"] == "VERSION_PRUEBA"
    assert r["certificado"] is False


def test_fila_duplicada():
    registros = [
        fila(8, "1.1", 100, -20, 80),
        fila(8, "1.1", 100, -20, 80),
    ]

    with pytest.raises(
        ValueError,
        match="Fila ESTRUCTURA duplicada",
    ):
        agrupar_estructura(registros, "VERSION_PRUEBA")


def test_fila_duplicada_con_nivel_diferente():
    registros = [
        fila(8, "1.1", 100, -20, 80),
        fila(8, "2.1", 100, -20, 80),
    ]

    with pytest.raises(ValueError):
        agrupar_estructura(registros, "VERSION_PRUEBA")


def test_fila_sin_nivel_duplicada():
    registros = [
        fila(1618, None, 0, 0, 0),
        fila(1618, None, 0, 0, 0),
    ]

    with pytest.raises(ValueError):
        agrupar_estructura(registros, "VERSION_PRUEBA")


def test_sin_nivel_conserva_importes():
    registros = [
        fila(1618, None, "100.25", "-20.10", "80.15"),
    ]

    r = agrupar_estructura(registros, "VERSION_PRUEBA")

    assert r["cantidad_sin_nivel"] == 1
    assert r["cantidad_niveles"] == 0

    excepcion = r["sin_nivel"][0]

    assert excepcion["debito_original"] == "100.25"
    assert excepcion["credito_original"] == "-20.10"
    assert excepcion["neto_original"] == "80.15"
    assert excepcion["certificado"] is False


def test_sin_nivel_distingue_ausencia_de_cero():
    registros = [
        fila(1618, None, None, 0, None),
    ]

    r = agrupar_estructura(registros, "VERSION_PRUEBA")

    excepcion = r["sin_nivel"][0]

    assert excepcion["debito_original"] is None
    assert excepcion["credito_original"] == "0"
    assert excepcion["neto_original"] is None


def test_sin_nivel_rechaza_importe_invalido():
    registros = [
        fila(1618, None, "NO_NUMERICO", 0, 0),
    ]

    with pytest.raises(ValueError):
        agrupar_estructura(registros, "VERSION_PRUEBA")


def test_integridad_monetaria_correcta():
    registros = [
        fila(8, "1.1", "100.25", "-20.10", "80.15"),
    ]

    r = agrupar_estructura(registros, "VERSION_PRUEBA")
    nivel = r["niveles"][0]

    assert nivel["diferencia_integridad"] == "0.00"
    assert nivel["estado_integridad"] == "INTEGRIDAD_CORRECTA"
    assert nivel["certificado"] is False


def test_integridad_monetaria_diferente():
    registros = [
        fila(8, "1.1", "100", "-20", "75"),
    ]

    r = agrupar_estructura(registros, "VERSION_PRUEBA")
    nivel = r["niveles"][0]

    assert Decimal(
        nivel["diferencia_integridad"]
    ) == Decimal("-5")

    assert nivel["estado_integridad"] == "DIFERENCIA_INTEGRIDAD"
    assert nivel["neto_estructura_actual"] == "75"
    assert nivel["certificado"] is False


def test_integridad_no_compensa_entre_niveles():
    registros = [
        fila(8, "1.1", 100, -20, 75),
        fila(9, "2.1", 100, -20, 85),
    ]

    r = agrupar_estructura(registros, "VERSION_PRUEBA")
    niveles = {n["nivel"]: n for n in r["niveles"]}

    assert niveles["1.1"]["estado_integridad"] == (
        "DIFERENCIA_INTEGRIDAD"
    )

    assert niveles["2.1"]["estado_integridad"] == (
        "DIFERENCIA_INTEGRIDAD"
    )

    assert r["certificado"] is False
