from decimal import Decimal
import pytest
from app.services.fase2.agrupacion_canje import agrupar_canje


def fila(linea, **extras):
    return {"tipo_insumo": "CANT", "id_archivo": 1254, "linea_origen": linea,
            "cuenta": "017-CANJE", "tipo_tarjeta": "DEBITO", "canal": "Manual",
            "tx": "02", "vl_total": "10.25", "vl_interc": "-0.25",
            "comision_op_exitosas": None, "tii_recibida": None, **extras}


def test_agrupacion_decimal_exacta():
    r = agrupar_canje([fila(1), fila(2)])
    assert r["cantidad_agrupada"] == 2
    assert r["grupos"][0]["vl_total"] == "20.50"
    assert r["grupos"][0]["vl_interc"] == "-0.50"


def test_sin_cuenta_no_contamina_totales():
    x = fila(1); x["cuenta"] = ""
    r = agrupar_canje([x])
    assert r["cantidad_agrupada"] == 0
    assert len(r["sin_clasificar"]) == 1


def test_registros_totales_no_se_suman():
    x = fila(1); x["tx"] = "03"
    r = agrupar_canje([x])
    assert len(r["controles"]) == 1
    assert r["grupos"] == []


def test_no_duplica_linea_archivo():
    with pytest.raises(ValueError, match="duplicado"):
        agrupar_canje([fila(1), fila(1)])


def test_rechaza_float():
    x = fila(1); x["vl_total"] = 0.1
    with pytest.raises(ValueError, match="float"):
        agrupar_canje([x])


def test_separa_caet_cant():
    x = fila(2); x["tipo_insumo"] = "CAET"
    r = agrupar_canje([fila(1), x])
    assert len(r["grupos"]) == 2


def test_no_muta_entrada():
    x = fila(1); original = x.copy()
    agrupar_canje([x]); assert x == original
