from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.fase2.reporte_pmd_inc59 import enriquecer


def reporte_base():
    return {
        "id_jornada": 5683,
        "certificado": False,
        "columnas": [str(i) for i in range(11)],
        "detalle": [{"cuenta": "299095302"}],
        "filas": [{"cuenta": "299095302", "diferencia": None}],
        "indicadores": {"cruces": 0},
    }


def filas_pmd():
    return [{
        "id_archivo": 5041,
        "numero_linea": 3,
        "NIVEL": "1.1",
        "ES_CONTROL": False,
        "DEBITO_VALOR": Decimal("100.25"),
        "CREDITO_VALOR": Decimal("30.10"),
        "DEBITO_NETO": Decimal("100.25"),
        "CREDITO_NETO": Decimal("30.10"),
        "TOTAL": Decimal("70.15"),
    }]


def test_conserva_reporte_base():
    base = reporte_base()
    resultado = enriquecer(base, filas_pmd())

    assert resultado["columnas"] == base["columnas"]
    assert resultado["detalle"] == base["detalle"]
    assert resultado["filas"] == base["filas"]
    assert resultado["indicadores"] == base["indicadores"]
    assert "diagnostico_pmd_inc59" not in base


def test_diagnostico_no_certificado():
    resultado = enriquecer(reporte_base(), filas_pmd())
    pmd = resultado["diagnostico_pmd_inc59"]

    assert resultado["certificado"] is False
    assert pmd["certificado"] is False
    assert pmd["cantidad_registros"] == 1
    assert pmd["archivos_origen"] == [5041]
    assert pmd["detalle_niveles"][0]["certificado"] is False


def test_rechaza_reporte_certificado():
    base = reporte_base()
    base["certificado"] = True

    with pytest.raises(ValueError):
        enriquecer(base, filas_pmd())


def test_rechaza_columnas_invalidas():
    base = reporte_base()
    base["columnas"] = ["cuenta"]

    with pytest.raises(ValueError):
        enriquecer(base, filas_pmd())


def test_sin_pmd():
    resultado = enriquecer(reporte_base(), [])
    pmd = resultado["diagnostico_pmd_inc59"]

    assert pmd["cantidad_registros"] == 0
    assert pmd["detalle_niveles"] == []
    assert pmd["certificado"] is False


def test_api_jornada_invalida():
    with TestClient(app) as cliente:
        respuesta = cliente.get(
            "/api/v1/jornadas/0/reporte-maestro-pmd-inc59"
        )

    assert respuesta.status_code == 422


def test_api_error_servicio():
    with patch(
        "app.api.reporte_pmd_inc59.consultar",
        side_effect=ValueError("Error controlado"),
    ):
        with TestClient(app) as cliente:
            respuesta = cliente.get(
                "/api/v1/jornadas/5683/reporte-maestro-pmd-inc59"
            )

    assert respuesta.status_code == 503


def test_api_registrada():
    rutas = app.openapi()["paths"]

    ruta = (
        "/api/v1/jornadas/{id_jornada}/"
        "reporte-maestro-pmd-inc59"
    )

    assert ruta in rutas
    assert "get" in rutas[ruta]


def test_api_jornada_inexistente():
    with patch(
        "app.api.reporte_pmd_inc59.consultar",
        side_effect=ValueError("Jornada inexistente"),
    ):
        with TestClient(app) as cliente:
            respuesta = cliente.get(
                "/api/v1/jornadas/999999/reporte-maestro-pmd-inc59"
            )

    assert respuesta.status_code == 404


def test_api_error_integridad():
    with patch(
        "app.api.reporte_pmd_inc59.consultar",
        side_effect=ValueError("Linea PMD duplicada"),
    ):
        with TestClient(app) as cliente:
            respuesta = cliente.get(
                "/api/v1/jornadas/5683/reporte-maestro-pmd-inc59"
            )

    assert respuesta.status_code == 503


def test_consultar_misma_jornada():
    from app.services.fase2.reporte_pmd_inc59 import consultar

    base = reporte_base()
    filas = filas_pmd()

    with patch(
        "app.services.fase2.reporte_pmd_inc59.consultar_base",
        return_value=base,
    ) as consulta_base:
        with patch(
            "app.services.fase2.reporte_pmd_inc59.leer_jornada",
            return_value=filas,
        ) as consulta_pmd:
            resultado = consultar(5683)

    consulta_base.assert_called_once_with(5683)
    consulta_pmd.assert_called_once_with(5683)

    assert resultado["id_jornada"] == 5683
    assert resultado["certificado"] is False
    assert resultado["diagnostico_pmd_inc59"]["id_jornada"] == 5683
