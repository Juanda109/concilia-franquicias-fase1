import pytest

from app.parsers import caet, cant


@pytest.mark.parametrize("modulo", [caet, cant])
@pytest.mark.parametrize(
    "tx,tipo,valor,esperado",
    [
        ("22", "EFIPAGO", "15000", -15000),
        ("22", "DEBITO", "15000", 15000),
        ("02", "EFIPAGO", "15000", 15000),
        ("22", "EFIPAGO", "", None),
        ("22", "EFIPAGO", "INVALIDO", None),
    ]
)
def test_valor_intercambio(
    modulo, tx, tipo, valor, esperado
):
    assert modulo._vl_interc(
        tx, tipo, valor
    ) == esperado


@pytest.mark.parametrize("modulo", [caet, cant])
@pytest.mark.parametrize(
    "tx,bin_dest,esperado",
    [
        ("02", "123456", 7450),
        ("02", "439467", None),
        ("06", "123456", None),
    ]
)
def test_comision_operaciones_exitosas(
    modulo, tx, bin_dest, esperado
):
    assert modulo._comision_op_exitosas(
        tx, bin_dest
    ) == esperado


@pytest.mark.parametrize("modulo", [caet, cant])
@pytest.mark.parametrize(
    "tipo,tx,total,interc,esperado",
    [
        ("CREDITO", "26", "20000", 5000, 15000),
        ("CREDITO", "26", "20000", None, 20000),
        ("DEBITO", "26", "20000", 5000, None),
        ("CREDITO", "02", "20000", 5000, None),
    ]
)
def test_tii_recibida(
    modulo, tipo, tx, total, interc, esperado
):
    assert modulo._tii_recibida(
        tipo, tx, total, interc
    ) == esperado


@pytest.mark.parametrize("modulo", [caet, cant])
@pytest.mark.parametrize(
    "bin_dest,tipo,canal,tx,esperado",
    [
        (
            "462550", "DEBITO", "ELECTRONICO", "02",
            "017-CANJE RECIBIDO TARJETA DEBITO REGALO"
        ),
        (
            "417704", "DEBITO", "Manual", "06",
            "017-CANJE RECIBIDO TARJETA DEBITO REGALO"
        ),
        ("462550", "DEBITO", "CNB", "02", ""),
        ("462550", "CREDITO", "ELECTRONICO", "02", ""),
    ]
)
def test_cuenta_880(
    modulo, bin_dest, tipo, canal, tx, esperado
):
    assert modulo._cuenta_880(
        bin_dest, tipo, canal, tx
    ) == esperado


@pytest.mark.parametrize("modulo", [caet, cant])
@pytest.mark.parametrize(
    "cod_error,cuenta,cuenta_880,comision,esperado",
    [
        (
            "00", "017-CANJE", "", "",
            (True, "CLASIFICACION_CUENTA")
        ),
        (
            "00", "", "017-REGALO", "",
            (True, "CLASIFICACION_CUENTA_880")
        ),
        (
            "00", "", "", "017-COMISION",
            (True, "CLASIFICACION_COMISION")
        ),
        (
            "99", "", "", "",
            (False, "COD_ERROR_NO_APLICABLE")
        ),
        (
            "00", "", "", "",
            (False, "SIN_CLASIFICACION_FUNCIONAL")
        ),
    ]
)
def test_filtro_persistencia(
    modulo, cod_error, cuenta, cuenta_880,
    comision, esperado
):
    assert modulo._persiste(
        cod_error, cuenta, cuenta_880, comision
    ) == esperado


@pytest.mark.parametrize("modulo", [caet, cant])
def test_persistencia_comision_con_codigo_error(modulo):
    comision = modulo._comision_op_exitosas(
        "02", "123456"
    )

    cuenta_comision = modulo._cuenta_comision(
        "DEBITO",
        "ELECTRONICO",
        "02",
        comision,
        None
    )

    persistir, motivo = modulo._persiste(
        "99",
        "",
        "",
        cuenta_comision
    )

    assert persistir is True
    assert motivo == "CLASIFICACION_COMISION"
