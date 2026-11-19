"""Paridad INC021 contra plantilla maestra identificada."""

import hashlib
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.services.fase2.paridad_plantilla_inc021 import (
    cargar_formulas,
    evaluar,
    DependenciaNoResuelta,
)


OBJETIVOS = (
    "F42", "G42",
    "F56", "G56",
    "F98", "G98",
    "F99", "G99",
    "F122", "G122",
    "F134", "G134",
    "F207", "G207",
    "F208", "G208",
    "F210", "G210",
    "G211",
)

FORMULAS_CONTROL = {
    "F210": "=+F208+F122+F99+F4+F5",
    "G210": "=+G208+G122+G99+G4+G5",
    "G211": "=+F210-G210",
}


@pytest.fixture(scope="module")
def plantilla():
    nombre = os.getenv("CONCILIA_INC021_PLANTILLA")
    checksum = os.getenv("CONCILIA_INC021_SHA256")

    if not nombre or not checksum:
        pytest.skip("Plantilla INC021 no configurada")

    ruta = Path(nombre).resolve(strict=True)

    if not ruta.is_file():
        raise AssertionError("Plantilla inexistente")

    actual = hashlib.sha256(ruta.read_bytes()).hexdigest()

    assert actual.lower() == checksum.lower(), (
        "La plantilla cambi? desde la validaci?n"
    )

    libro = load_workbook(
        ruta,
        data_only=False,
        read_only=True,
        keep_links=True,
    )

    try:
        hoja = libro["PLANTILLA (2)"]

        for celda, esperada in FORMULAS_CONTROL.items():
            assert hoja[celda].value == esperada, (
                f"F?rmula modificada: {celda}"
            )
    finally:
        libro.close()

    formulas = cargar_formulas(ruta)

    libro = load_workbook(
        ruta,
        data_only=True,
        read_only=True,
    )

    try:
        hoja = libro["PLANTILLA (2)"]

        cache = {
            celda: hoja[celda].value
            for celda in OBJETIVOS
        }

        hoja.reset_dimensions()

        valores = {
            celda.coordinate: celda.value
            for fila in hoja.iter_rows()
            for celda in fila
            if celda.value is not None
        }
    finally:
        libro.close()

    return formulas, valores, cache


@pytest.mark.parametrize("celda", OBJETIVOS)
def test_paridad_maestra_inc021(plantilla, celda):
    formulas, valores, cache = plantilla

    try:
        resultado = evaluar(celda, valores, formulas)
    except DependenciaNoResuelta as exc:
        pytest.fail(
            f"{celda}: dependencia no resuelta: {exc}"
        )

    excel = cache[celda]

    assert excel is not None, (
        f"{celda}: Excel no contiene valor almacenado"
    )

    assert not isinstance(excel, bool)
    assert isinstance(excel, (int, float, Decimal))

    try:
        calculado = Decimal(str(resultado))
        esperado = Decimal(str(excel))
    except (InvalidOperation, TypeError, ValueError) as exc:
        pytest.fail(f"{celda}: importe no comparable: {exc}")

    assert calculado.is_finite()
    assert esperado.is_finite()

    assert calculado == esperado, (
        f"{celda}: Python={calculado}, Excel={esperado}"
    )
