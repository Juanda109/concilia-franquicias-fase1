from datetime import date
from decimal import Decimal

import pytest

from app.services.normalizacion_credibanco import (
    normalizar_cant,
    NormalizacionCredibancoError,
    CUENTA_REPRESENTACION,
)


def registro(linea=221, valor="001850000"):
    return {
        "numero_linea": linea,
        "TX": "36",
        "BIN_DEST": "492489",
        "VL_TOTAL": valor,
        "VL_INTERC": 1850000,
        "CUENTA": CUENTA_REPRESENTACION,
    }


def normalizar(registros):
    return normalizar_cant(
        registros=registros,
        fecha_contable=date(2026, 10, 20),
        id_archivo=287,
        correlation_id="prueba-cant",
    )


def test_cant_utiliza_vl_total():
    filas = normalizar([registro()])

    assert len(filas) == 1
    assert filas[0]["valor"] == Decimal("1850000")
    assert filas[0]["concepto"] == "VL_TOTAL"
    assert filas[0]["linea_origen"] == 221
    assert filas[0]["cuenta"] == CUENTA_REPRESENTACION


def test_cant_cuatro_movimientos():
    valores = (
        "001850000",
        "000132000",
        "000056592",
        "000169829",
    )

    registros = [
        registro(221 + indice, valor)
        for indice, valor in enumerate(valores)
    ]

    filas = normalizar(registros)

    assert len(filas) == 4

    total = sum(
        (fila["valor"] for fila in filas),
        Decimal("0"),
    )

    assert total == Decimal("2208421")


def test_cant_rechaza_cuenta_no_autorizada():
    movimiento = registro()
    movimiento["CUENTA"] = "OTRA CUENTA"

    with pytest.raises(NormalizacionCredibancoError):
        normalizar([movimiento])


@pytest.mark.parametrize(
    "valor",
    ["", "INVALIDO", "NaN", "Infinity"],
)
def test_cant_rechaza_importe_invalido(valor):
    with pytest.raises(NormalizacionCredibancoError):
        normalizar([registro(valor=valor)])


def test_cant_rechaza_linea_duplicada():
    with pytest.raises(
        NormalizacionCredibancoError,
        match="duplicada",
    ):
        normalizar([
            registro(221),
            registro(221),
        ])
