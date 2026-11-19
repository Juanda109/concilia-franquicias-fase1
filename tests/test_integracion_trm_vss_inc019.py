from datetime import date
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from psycopg import OperationalError

from app.api import visa_documental_inc018 as api

JORNADA = 6606
FECHA = date(2026, 11, 12)

ARCHIVO = {
    "id_archivo": 1,
    "fecha_contable": FECHA,
}

def estado_trm(trm=None):
    return {
        "id_jornada": JORNADA,
        "fecha_contable": FECHA.isoformat(),
        "estado": "TRM_CONFIRMADA" if trm else "SIN_TRM_CONFIRMADA",
        "trm": trm,
    }

def confirmacion():
    return {
        "version": 1,
        "fecha_referencia": FECHA.isoformat(),
        "trm_aplicada": "4000.0000",
    }

def ejecutar(estado):
    with (
        patch.object(api, "recuperar_vss", return_value=(ARCHIVO, "VSS_SIMULADO")),
        patch.object(api, "consultar_trm_vigente", return_value=estado),
        patch.object(
            api,
            "integrar_vss",
            side_effect=lambda **kw: kw["trm_confirmada"],
        ),
    ):
        return api.consultar_visa_documental(JORNADA)

def test_sin_trm():
    assert ejecutar(estado_trm()) is None

def test_trm_confirmada():
    resultado = ejecutar(estado_trm(confirmacion()))
    assert resultado["estado"] == "TRM_CONFIRMADA"
    assert resultado["confirmada"] is True
    assert resultado["version"] == 1

def test_jornada_incorrecta():
    estado = estado_trm(confirmacion())
    estado["id_jornada"] = 9999
    with pytest.raises(HTTPException) as exc:
        ejecutar(estado)
    assert exc.value.status_code == 409

def test_fecha_contable_incorrecta():
    estado = estado_trm(confirmacion())
    estado["fecha_contable"] = "2026-10-26"
    with pytest.raises(HTTPException) as exc:
        ejecutar(estado)
    assert exc.value.status_code == 409

def test_error_postgresql():
    with (
        patch.object(api, "recuperar_vss", return_value=(ARCHIVO, "VSS_SIMULADO")),
        patch.object(
            api,
            "consultar_trm_vigente",
            side_effect=OperationalError("Fallo simulado"),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            api.consultar_visa_documental(JORNADA)

    assert exc.value.status_code == 503


@pytest.mark.parametrize(
    "cambios",
    [
        {"version": 0},
        {"version": -1},
        {"version": 1.5},
        {"fecha_referencia": "2026-10-26"},
        {"trm_aplicada": "-1.0000"},
        {"trm_aplicada": "0.0000"},
        {"trm_aplicada": "NaN"},
        {"trm_aplicada": "4000.12345"},
    ],
)
def test_inc019_rechaza_trm_invalida(cambios):
    trm = {
        **confirmacion(),
        **cambios,
    }

    with pytest.raises(HTTPException) as exc:
        ejecutar(estado_trm(trm))

    assert exc.value.status_code == 409
