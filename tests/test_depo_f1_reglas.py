import pytest

from app.parsers.depo import _persiste, _tasa_intercambio


@pytest.mark.parametrize("indicador", [
    "010", "011", "012", "110", "111", "112"
])
def test_regla_3_cnb_persiste_los_seis_indicadores(indicador):
    registro = {
        "TIPO_MOVIMIENTO": "99",
        "INDICADOR_CASH_BACK": indicador,
        "TASA_DE_INTERCAMBIO": 0,
    }
    assert _persiste(registro) is True


@pytest.mark.parametrize("movimiento", ["02", "06", "26", "42"])
def test_regla_2_persiste_tipos_de_movimiento(movimiento):
    registro = {
        "TIPO_MOVIMIENTO": movimiento,
        "INDICADOR_CASH_BACK": "999",
        "TASA_DE_INTERCAMBIO": 0,
    }
    assert _persiste(registro) is True


def test_regla_1_excluye_tipo_05():
    registro = {
        "TIPO_MOVIMIENTO": "05",
        "INDICADOR_CASH_BACK": "010",
        "TASA_DE_INTERCAMBIO": 500,
    }
    assert _persiste(registro) is False


def test_regla_5_persiste_tasa_diferente_de_cero():
    registro = {
        "TIPO_MOVIMIENTO": "99",
        "INDICADOR_CASH_BACK": "999",
        "TASA_DE_INTERCAMBIO": 1,
    }
    assert _persiste(registro) is True


def test_regla_6_descarta_registro_sin_condicion():
    registro = {
        "TIPO_MOVIMIENTO": "99",
        "INDICADOR_CASH_BACK": "999",
        "TASA_DE_INTERCAMBIO": 0,
    }
    assert _persiste(registro) is False


def test_movimiento_26_invierte_signo_de_tasa():
    registro = {
        "TIPO_MOVIMIENTO": "26",
        "VALOR_TOTAL": "1000",
        "VALOR_INTERCAMBIO_2": "300",
    }
    assert _tasa_intercambio(registro) == -700


def test_otros_movimientos_conservan_signo_de_tasa():
    registro = {
        "TIPO_MOVIMIENTO": "02",
        "VALOR_TOTAL": "1000",
        "VALOR_INTERCAMBIO_2": "300",
    }
    assert _tasa_intercambio(registro) == 700
