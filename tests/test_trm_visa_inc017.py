from datetime import date
from decimal import Decimal

import pytest

from app.services.fase2.trm_visa_inc017 import (
    ConfirmacionTRM,
    ErrorTRMVisa,
    convertir_usd_cop,
    validar_trm,
)


def confirmacion(**cambios):
    datos = {
        "id_jornada": 6606,
        "fecha_contable": date(2026, 11, 12),
        "fecha_referencia": date(2026, 11, 12),
        "trm_oficial": Decimal("4100.0000"),
        "trm_aplicada": Decimal("4100.0000"),
        "fuente": "TASA_FICTICIA_PARA_PRUEBAS",
        "modificada_manualmente": False,
        "justificacion": None,
        "usuario_confirmacion": "USUARIO_PRUEBA",
        "version": 1,
    }
    datos.update(cambios)
    return ConfirmacionTRM(**datos)


def test_conversion_documental():
    r = convertir_usd_cop("125.00", confirmacion())

    assert r["importe_cop"] == "512500.00"
    assert r["importe_usd"] == "125.00"
    assert r["version_trm"] == 1
    assert r["certificado"] is False
    assert r["conciliado_host"] is False


def test_conserva_importe_original():
    r = convertir_usd_cop("-125.00", confirmacion())

    assert r["importe_usd"] == "-125.00"
    assert r["importe_cop"] == "-512500.00"


def test_cambio_manual_justificado():
    c = confirmacion(
        trm_aplicada=Decimal("4200.0000"),
        modificada_manualmente=True,
        justificacion="Ajuste autorizado para prueba",
        version=2,
    )

    r = convertir_usd_cop("125.00", c)

    assert r["importe_cop"] == "525000.00"
    assert r["version_trm"] == 2


def test_cambio_manual_sin_justificacion():
    with pytest.raises(ErrorTRMVisa):
        confirmacion(
            trm_aplicada=Decimal("4200.0000"),
            modificada_manualmente=True,
            justificacion=None,
        )


def test_fecha_incorrecta():
    with pytest.raises(ErrorTRMVisa):
        confirmacion(
            fecha_referencia=date(2026, 11, 13)
        )


def test_sin_confirmacion():
    with pytest.raises(ErrorTRMVisa):
        confirmacion(confirmada=False)


def test_usuario_obligatorio():
    with pytest.raises(ErrorTRMVisa):
        confirmacion(usuario_confirmacion="")


def test_no_acepta_tasa_diferente_sin_cambio_manual():
    with pytest.raises(ErrorTRMVisa):
        confirmacion(
            trm_aplicada=Decimal("4200.0000")
        )


@pytest.mark.parametrize(
    "valor",
    ["0", "-1", "NaN", "Infinity", "4100.12345", "abc", 4100.0, True],
)
def test_tasas_invalidas(valor):
    with pytest.raises(ErrorTRMVisa):
        validar_trm(valor)


@pytest.mark.parametrize(
    "valor",
    ["NaN", "Infinity", "1.001", 1.2, True],
)
def test_importes_invalidos(valor):
    with pytest.raises(ErrorTRMVisa):
        convertir_usd_cop(valor, confirmacion())


def test_redondeo_controlado():
    c = confirmacion(
        trm_oficial=Decimal("4000.0001"),
        trm_aplicada=Decimal("4000.0001"),
    )

    r = convertir_usd_cop("50.00", c)

    assert r["importe_cop"] == "200000.01"


def test_version_invalida():
    with pytest.raises(ErrorTRMVisa):
        confirmacion(version=0)
