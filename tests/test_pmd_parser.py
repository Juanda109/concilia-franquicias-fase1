import os
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers.pmd import PMDParser


def test_pmd_archivo_real():
    ruta = os.environ.get("PMD_SAMPLE")

    if not ruta:
        pytest.skip("PMD_SAMPLE no configurado")

    archivo = Path(ruta)

    if not archivo.is_file():
        pytest.skip("Muestra PMD no disponible")

    resultado = PMDParser().parse(archivo)

    assert resultado.errors == []
    assert len(resultado.records) == 332

    primero = resultado.records[0]

    assert primero["PRODUCTO_SERVICIO"] == "TARJETA DE CREDITO"
    assert primero["NIVEL"] == "1"
    assert primero["DEBITO_VALOR"] == Decimal("25059284565")

    controles = {
        c["codigo"]: c["obtenido"]
        for c in resultado.controls
    }

    assert controles["TOTAL_REGISTROS"] == 332
    assert controles["REGISTROS_CONTROL"] == 1


def test_pmd_nombre_invalido(tmp_path):
    archivo = tmp_path / "archivo_invalido.xls"
    archivo.write_bytes(b"NO_ES_EXCEL")

    resultado = PMDParser().parse(archivo)

    assert len(resultado.records) == 0
    assert resultado.errors[0].codigo == "NOMBRE_INVALIDO"


from openpyxl import Workbook


def crear_pmd_sintetico(tmp_path, fila_datos):
    archivo = tmp_path / "PMDGeneralEntidad20261002.xlsx"

    libro = Workbook()
    hoja = libro.active
    hoja.title = "PMD"

    hoja.append([
        "Producto / Servicio", "Nivel",
        "DEBITO", None, None, None, None,
        "CREDITO", None, None, None, None,
        "Total"
    ])

    hoja.append([
        None, None,
        "Cantidad", "Valor",
        "Comisión Intercambio",
        "Comisión Administrativa", "Neto",
        "Cantidad", "Valor",
        "Comisión Intercambio",
        "Comisión Administrativa", "Neto",
        None
    ])

    hoja.append(fila_datos)
    libro.save(archivo)

    return archivo


def fila_pmd_valida():
    return [
        "TARJETA DE CREDITO",
        "1.1.1",
        10,
        100000,
        500,
        200,
        100700,
        5,
        50000,
        300,
        100,
        50400,
        50300
    ]


def test_pmd_nivel_jerarquico(tmp_path):
    archivo = crear_pmd_sintetico(
        tmp_path, fila_pmd_valida()
    )

    resultado = PMDParser().parse(archivo)

    assert resultado.errors == []
    assert len(resultado.records) == 1
    assert resultado.records[0]["NIVEL"] == "1.1.1"


def test_pmd_nivel_invalido(tmp_path):
    fila = fila_pmd_valida()
    fila[1] = "1.A.1"

    archivo = crear_pmd_sintetico(tmp_path, fila)
    resultado = PMDParser().parse(archivo)

    assert len(resultado.records) == 0
    assert resultado.errors[0].codigo == "REGISTRO_INVALIDO"


@pytest.mark.parametrize(
    "valor",
    ["NO_NUMERICO", "NaN", "Infinity"]
)
def test_pmd_importe_invalido(tmp_path, valor):
    fila = fila_pmd_valida()
    fila[3] = valor

    archivo = crear_pmd_sintetico(tmp_path, fila)
    resultado = PMDParser().parse(archivo)

    assert len(resultado.records) == 0
    assert resultado.errors[0].codigo == "NUMERO_INVALIDO"


def test_pmd_cantidad_negativa(tmp_path):
    fila = fila_pmd_valida()
    fila[2] = -1

    archivo = crear_pmd_sintetico(tmp_path, fila)
    resultado = PMDParser().parse(archivo)

    assert len(resultado.records) == 0
    assert resultado.errors[0].codigo == "NUMERO_INVALIDO"


def test_pmd_precision_decimal(tmp_path):
    fila = fila_pmd_valida()
    fila[3] = "123456789.45"
    fila[4] = "1234.67"

    archivo = crear_pmd_sintetico(tmp_path, fila)
    resultado = PMDParser().parse(archivo)

    assert resultado.errors == []

    registro = resultado.records[0]

    assert registro["DEBITO_VALOR"] == Decimal("123456789.45")
    assert registro["DEBITO_COMISION_INTERCAMBIO"] == Decimal("1234.67")


def test_pmd_registro_control(tmp_path):
    fila = fila_pmd_valida()
    fila[0] = "TOTAL PRODUCTOS PMD"

    archivo = crear_pmd_sintetico(tmp_path, fila)
    resultado = PMDParser().parse(archivo)

    assert resultado.errors == []
    assert resultado.records[0]["ES_CONTROL"] is True

    controles = {
        c["codigo"]: c["obtenido"]
        for c in resultado.controls
    }

    assert controles["REGISTROS_CONTROL"] == 1


def test_pmd_cantidad_fraccionaria(tmp_path):
    fila = fila_pmd_valida()
    fila[2] = 1.5

    archivo = crear_pmd_sintetico(tmp_path, fila)
    resultado = PMDParser().parse(archivo)

    assert len(resultado.records) == 0
    assert resultado.errors[0].codigo == "NUMERO_INVALIDO"
