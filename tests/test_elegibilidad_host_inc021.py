import pytest

from app.services.fase2.elegibilidad_host_inc021 import (
    SINTETICO,
    ORIGEN_NO_VERIFICADO,
    ELEGIBLE_REVISION,
    clasificar_movimiento,
    evaluar_lote,
)


def test_ha22_sintetico():
    resultado = clasificar_movimiento({
        "tx_host": "HA22",
        "cuenta": "299095038",
        "referencia": "S",
        "concepto": "PRUEBA SINTETICA - NO CONCILIAR",
    })

    assert resultado.estado == SINTETICO
    assert resultado.puede_homologar is False


def test_ha26_sintetico():
    resultado = clasificar_movimiento({
        "tx_host": "HA26",
        "cuenta": "299095843",
        "referencia": "S",
        "concepto": "PRUEBA SINTETICA - NO CONCILIAR",
    })

    assert resultado.estado == SINTETICO


def test_ha32_sin_procedencia():
    resultado = clasificar_movimiento({
        "tx_host": "HA32",
        "cuenta": "299095038",
        "referencia": None,
        "concepto": None,
    })

    assert resultado.estado == ORIGEN_NO_VERIFICADO


def test_sin_indicador_no_significa_real():
    resultado = clasificar_movimiento({
        "concepto": "MOVIMIENTO HOST",
        "referencia": "123",
    })

    assert resultado.estado == ORIGEN_NO_VERIFICADO


def test_procedencia_documentada_no_certifica():
    resultado = clasificar_movimiento(
        {
            "concepto": "MOVIMIENTO HOST",
            "referencia": "123",
        },
        procedencia_verificada=True,
    )

    assert resultado.estado == ELEGIBLE_REVISION
    assert resultado.puede_homologar is False
    assert resultado.certificado is False


def test_lote_no_homologa():
    lote = evaluar_lote([
        {
            "tx_host": "HA22",
            "cuenta": "299095038",
            "referencia": "S",
            "concepto": "PRUEBA SINTETICA - NO CONCILIAR",
            "linea_origen": 4,
        },
        {
            "tx_host": "HA32",
            "cuenta": "299095038",
            "referencia": None,
            "concepto": None,
            "linea_origen": 4,
        },
    ])

    assert len(lote["movimientos"]) == 2
    assert lote["movimientos"][0]["estado"] == SINTETICO
    assert lote["movimientos"][1]["estado"] == ORIGEN_NO_VERIFICADO

    assert lote["certificado"] is False
    assert lote["conciliado_host"] is False
    assert lote["homologado_contablemente"] is False
