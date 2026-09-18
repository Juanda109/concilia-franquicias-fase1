"""Descripcion del listado = el COMERCIO, no el estado (Fabian, 27/08).

Contra el payload REAL capturado en dev (usuario de pruebas de Jessica,
tarjeta 4593...9784, 14/04/2026): descProvision traia "ACEPTADA" (un estado)
y placeOperation "ASCR" (un codigo); el nombre real del comercio viaja en el
5o bloque de observations. Jessica garantiza que el patron se mantiene.
"""

from application.trx.aso_rules import parse_movimientos_operations

PAYLOAD_REAL = {
    "data": [{
        "operations": [{
            "id": "000007731",
            "descProvision": "ACEPTADA",
            "placeOperation": "ASCR",
            "amountOperation": {"amount": "96930", "currency": "COP"},
            "dateOper": "2026-04-14",
            "hourOperation": "083740",
            "interest": 8702.64,
            "statementDetail": {"statementId": "0102", "movementId": "000009"},
            "observations": "01CRUZADA      |CONDONACION      |    |051   05|EDS COMBUS LLANOS   |10000000013|",
            "responseOperati": "660926",
            "dateReverse": "",
        }]
    }]
}


def test_payload_real_muestra_el_comercio():
    movs = parse_movimientos_operations(PAYLOAD_REAL)
    assert movs[0]["descripcion"] == "EDS COMBUS LLANOS"


def test_sin_bloques_cae_a_la_cascada_clasica():
    import copy
    p = copy.deepcopy(PAYLOAD_REAL)
    p["data"][0]["operations"][0]["observations"] = "OPER FINALIZADA CON EXITO"
    movs = parse_movimientos_operations(p)
    assert movs[0]["descripcion"] == "ACEPTADA"   # descProvision, como antes


def test_bloque_de_comercio_vacio_tambien_cae_al_respaldo():
    import copy
    p = copy.deepcopy(PAYLOAD_REAL)
    p["data"][0]["operations"][0]["observations"] = "01X |Y | |051 05|   |123|"
    movs = parse_movimientos_operations(p)
    assert movs[0]["descripcion"] == "ACEPTADA"


def test_observaciones_crudas_se_conservan_para_la_clasificacion():
    movs = parse_movimientos_operations(PAYLOAD_REAL)
    assert "EDS COMBUS LLANOS" in movs[0]["observaciones"]
