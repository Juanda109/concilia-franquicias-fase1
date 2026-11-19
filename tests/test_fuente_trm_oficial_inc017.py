from datetime import date

import pytest

from app.services.fase2.fuente_trm_oficial_inc017 import (
    ErrorFuenteTRM,
    validar_respuesta_oficial,
)


FECHA = date(2026, 11, 12)


def registro(**cambios):
    datos = {
        "valor": "4100.0000",
        "unidad": "COP",
        "vigenciadesde": "2026-11-12T00:00:00.000",
        "vigenciahasta": "2026-11-12T00:00:00.000",
    }
    datos.update(cambios)
    return datos


def consultar(registros, verificada=True):
    return validar_respuesta_oficial(
        fecha_contable=FECHA,
        registros=registros,
        procedencia_verificada=verificada,
    )


def test_propuesta_oficial():
    r = consultar([registro()])
    assert r["trm_propuesta"] == "4100.0000"
    assert r["estado"] == "TRM_OFICIAL_PROPUESTA"
    assert r["confirmada"] is False


def test_fuente_no_verificada():
    r = consultar([registro()], False)
    assert r["estado"] == "SIN_FUENTE_OFICIAL"
    assert r["trm_propuesta"] is None


def test_sin_registros():
    r = consultar([])
    assert r["estado"] == "SIN_FUENTE_OFICIAL"


def test_vigencia_incluye_fecha():
    r = consultar([
        registro(
            vigenciadesde="2026-11-11T00:00:00",
            vigenciahasta="2026-11-13T00:00:00",
        )
    ])
    assert r["trm_propuesta"] == "4100.0000"


def test_fecha_fuera_de_vigencia():
    r = consultar([
        registro(
            vigenciadesde="2026-11-13T00:00:00",
            vigenciahasta="2026-11-14T00:00:00",
        )
    ])
    assert r["trm_propuesta"] is None


def test_moneda_incorrecta():
    with pytest.raises(ErrorFuenteTRM):
        consultar([registro(unidad="USD")])


def test_intervalo_invalido():
    with pytest.raises(ErrorFuenteTRM):
        consultar([
            registro(
                vigenciadesde="2026-11-13",
                vigenciahasta="2026-11-12",
            )
        ])


def test_multiples_tasas():
    with pytest.raises(ErrorFuenteTRM):
        consultar([registro(), registro()])


def test_no_certifica():
    r = consultar([registro()])
    assert r["certificado"] is False
    assert r["conciliado_host"] is False
