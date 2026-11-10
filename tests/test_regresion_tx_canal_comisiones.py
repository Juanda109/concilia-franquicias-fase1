import pytest

from app.parsers import caet, cant


@pytest.mark.parametrize("modulo", [caet, cant])
@pytest.mark.parametrize(
    "tx,esperado",
    [
        ("01", "Totales"),
        ("03", "Totales"),
        ("02", "02"),
        ("22", "22"),
        ("26", "26"),
        ("XX", "XX"),
    ]
)
def test_tx_normalizado(modulo, tx, esperado):
    assert modulo._tx_normalizado(tx) == esperado


@pytest.mark.parametrize("modulo", [caet, cant])
@pytest.mark.parametrize(
    "tx,xx,esperado",
    [
        ("Totales", "10", "Totales"),
        ("02", "  ", "Manual"),
        ("02", "10", "CNB"),
        ("02", "11", "CNB"),
        ("02", "12", "CNB"),
        ("02", "99", "ELECTRONICO"),
    ]
)
def test_clasificacion_canal(modulo, tx, xx, esperado):
    assert modulo._canal(tx, xx) == esperado


@pytest.mark.parametrize("modulo", [caet, cant])
@pytest.mark.parametrize(
    "tipo,canal,tx,comision,tii,esperado",
    [
        (
            "DEBITO", "ELECTRONICO", "02", 7450, None,
            "017-COMISIONES EXIT. TARJETA DEBITO ONLINE"
        ),
        (
            "DEBITO", "Manual", "02", 7450, None,
            "017-COMISIONES EXIT. TARJETA DEBITO ONLINE"
        ),
        (
            "DEBITO", "CNB", "02", 7450, None,
            ""
        ),
        (
            "CREDITO", "ELECTRONICO", "02", 7450, None,
            "017-CJE REC VISA NAL VR COM EXIT TC BATC"
        ),
        (
            "CREDITO", "Manual", "02", 7450, None,
            ""
        ),
        (
            "CREDITO", "ELECTRONICO", "26", None, 15000,
            "017-TII RECIBIDA EMISOR VISA OP REVER VENTAS"
        ),
        (
            "CREDITO", "ELECTRONICO", "26", None, 0,
            ""
        ),
        (
            "DEBITO", "ELECTRONICO", "06", None, None,
            ""
        ),
    ]
)
def test_clasificacion_cuenta_comision(
    modulo, tipo, canal, tx, comision, tii, esperado
):
    assert modulo._cuenta_comision(
        tipo, canal, tx, comision, tii
    ) == esperado
