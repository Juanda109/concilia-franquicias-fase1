from decimal import Decimal
from unittest.mock import patch

import pytest

from app.services.fase2.repositorio_pmd_inc58 import (
    normalizar,
    leer_jornada,
)


def test_normalizacion_pmd():
    fila = {
        "id_archivo": 5041,
        "linea_origen": 3,
        "producto_servicio": "PRUEBA SINTETICA 1",
        "nivel": "1.1",
        "es_control": False,
    }

    from app.services.fase2.repositorio_pmd_inc58 import CAMPOS

    for campo in CAMPOS:
        fila[campo.lower()] = Decimal("0")

    fila["debito_valor"] = Decimal("11747250.0000")

    resultado = normalizar(fila)

    assert resultado["id_archivo"] == 5041
    assert resultado["numero_linea"] == 3
    assert resultado["NIVEL"] == "1.1"
    assert resultado["DEBITO_VALOR"] == Decimal("11747250.0000")
    assert resultado["ES_CONTROL"] is False


@pytest.mark.parametrize("jornada", [0, -1, None, "5683", True])
def test_jornada_invalida(jornada):
    with pytest.raises(ValueError):
        leer_jornada(jornada)


def test_normalizacion_conserva_control():
    fila = {
        "id_archivo": 10,
        "linea_origen": 20,
        "producto_servicio": "TOTAL PRODUCTOS PMD",
        "nivel": "1",
        "es_control": True,
    }

    from app.services.fase2.repositorio_pmd_inc58 import CAMPOS

    for campo in CAMPOS:
        fila[campo.lower()] = None

    resultado = normalizar(fila)

    assert resultado["ES_CONTROL"] is True
    assert resultado["DEBITO_VALOR"] is None


def test_consulta_no_requerida_para_jornada_invalida():
    with patch(
        "app.services.fase2.repositorio_pmd_inc58.connection"
    ) as conexion:
        with pytest.raises(ValueError):
            leer_jornada(0)

        conexion.assert_not_called()


def test_integridad_correcta():
    from datetime import date
    from app.services.fase2.repositorio_pmd_inc58 import validar_integridad

    fecha = date(2026, 11, 10)
    archivos = [{"id_archivo": 5041, "fecha_contable": fecha}]
    filas = [{
        "id_archivo": 5041,
        "linea_origen": 3,
        "fecha_contable": fecha,
    }]

    assert validar_integridad(5683, fecha, archivos, filas)


@pytest.mark.parametrize("caso", [
    "MULTIPLES_ARCHIVOS",
    "SIN_DETALLE",
    "FECHA_ARCHIVO",
    "FECHA_DETALLE",
    "LINEA_DUPLICADA",
    "ARCHIVO_INCORRECTO",
])
def test_integridad_rechaza_anomalias(caso):
    from datetime import date
    from app.services.fase2.repositorio_pmd_inc58 import validar_integridad

    fecha = date(2026, 11, 10)

    archivos = [{
        "id_archivo": 5041,
        "fecha_contable": fecha,
    }]

    filas = [{
        "id_archivo": 5041,
        "linea_origen": 3,
        "fecha_contable": fecha,
    }]

    if caso == "MULTIPLES_ARCHIVOS":
        archivos.append({
            "id_archivo": 5042,
            "fecha_contable": fecha,
        })

    elif caso == "SIN_DETALLE":
        filas = []

    elif caso == "FECHA_ARCHIVO":
        archivos[0]["fecha_contable"] = date(2026, 11, 9)

    elif caso == "FECHA_DETALLE":
        filas[0]["fecha_contable"] = date(2026, 11, 9)

    elif caso == "LINEA_DUPLICADA":
        filas.append(dict(filas[0]))

    elif caso == "ARCHIVO_INCORRECTO":
        filas[0]["id_archivo"] = 9999

    with pytest.raises(ValueError):
        validar_integridad(5683, fecha, archivos, filas)
