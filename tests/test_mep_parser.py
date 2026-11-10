import os
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.parsers.mep import MEPParser, COLUMNS


def crear_mep(tmp_path, registros, encabezado=None):
    archivo = tmp_path / "mep_prueba.xlsx"
    libro = Workbook()
    hoja = libro.active
    hoja.append(list(encabezado or COLUMNS))

    for registro in registros:
        hoja.append(registro)

    libro.save(archivo)
    libro.close()
    return archivo


def fila_valida():
    fila = [None] * 18
    fila[0] = "0017"
    fila[1] = "196095001839"
    fila[2] = "COP"
    fila[5] = -1764920
    fila[7] = "20260706"
    fila[17] = 0
    return fila


def test_mep_archivo_real():
    ruta = os.environ.get("MEP_SAMPLE")

    if not ruta or not Path(ruta).is_file():
        pytest.skip("Muestra real MEP no disponible")

    resultado = MEPParser().parse(Path(ruta))

    assert resultado.errors == []
    assert len(resultado.records) == 2

    controles = {
        c["codigo"]: c["obtenido"]
        for c in resultado.controls
    }

    assert controles["TOTAL_REGISTROS"] == 2
    assert controles["SUMA_IMPORTE"] == Decimal("0")

    assert resultado.records[0]["CUENTA"] == "196095001839"
    assert resultado.records[0]["IMPORTE"] == Decimal("-1764920")


def test_mep_registro_valido(tmp_path):
    resultado = MEPParser().parse(
        crear_mep(tmp_path, [fila_valida()])
    )

    assert resultado.errors == []
    assert len(resultado.records) == 1
    assert resultado.records[0]["FECHA"] == "2026-07-06"
    assert resultado.records[0]["IMPORTE"] == Decimal("-1764920")


@pytest.mark.parametrize(
    "importe",
    ["INVALIDO", "NaN", "Infinity", "-Infinity"]
)
def test_mep_importe_invalido(tmp_path, importe):
    fila = fila_valida()
    fila[5] = importe

    resultado = MEPParser().parse(
        crear_mep(tmp_path, [fila])
    )

    assert len(resultado.records) == 0
    assert resultado.errors[0].codigo == "REGISTRO_INVALIDO"


@pytest.mark.parametrize(
    "fecha",
    ["20261301", "20260230", "FECHA_INVALIDA"]
)
def test_mep_fecha_invalida(tmp_path, fecha):
    fila = fila_valida()
    fila[7] = fecha

    resultado = MEPParser().parse(
        crear_mep(tmp_path, [fila])
    )

    assert len(resultado.records) == 0
    assert resultado.errors[0].codigo == "REGISTRO_INVALIDO"


def test_mep_cuenta_obligatoria(tmp_path):
    fila = fila_valida()
    fila[1] = None

    resultado = MEPParser().parse(
        crear_mep(tmp_path, [fila])
    )

    assert len(resultado.records) == 0
    assert resultado.errors[0].codigo == "REGISTRO_INVALIDO"


def test_mep_encabezado_invalido(tmp_path):
    encabezado = list(COLUMNS)
    encabezado[1] = "CUENTA_INCORRECTA"

    resultado = MEPParser().parse(
        crear_mep(
            tmp_path,
            [fila_valida()],
            encabezado=encabezado
        )
    )

    assert len(resultado.records) == 0
    assert resultado.errors[0].codigo == "HEADER_INVALIDO"
