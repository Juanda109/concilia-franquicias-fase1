from decimal import Decimal

from app.services.fase2.cierre_credibanco_v67 import construir_cierre


def _archivo(tipo, ident):
    return {
        "id_archivo": ident,
        "tipo_archivo": tipo,
        "fecha_contable": "2026-11-10",
        "estado_archivo": "PROCESADO",
        "estado_insumo": "PROCESADO",
    }


def test_cierre_retorna_totales_diagnosticos_desde_canje_persistido():
    canje = [{
        "id_archivo": 5046,
        "tipo_archivo": "CANT",
        "fecha_contable": "2026-11-10",
        "cuenta": "017-CANJE RECIBIDO TARJETA CREDITO PAGOS",
        "cuentas_comisiones": "",
        "tx": "02",
        "cod_error": "00",
        "cantidad": 4,
        "total_valor": Decimal("11747250.0000"),
        "total_intercambio": Decimal("0.0000"),
        "total_comision": None,
        "nulos_total": 0,
        "nulos_interc": 0,
        "nulos_comision": 4,
    }]
    archivos = [
        _archivo("CAET", 5036),
        _archivo("CANT", 5046),
        _archivo("DEPO", 5047),
        _archivo("CARTA_COMPENSACION", 5043),
        _archivo("HA22", 5035),
        _archivo("HA26", 5037),
        _archivo("HA32", 5038),
    ]
    resultado = construir_cierre(
        jornada={"id_jornada": 5683, "fecha_contable": "2026-11-10"},
        archivos=archivos,
        canje=canje,
        depo=[], carta=[], host=[], evidencia_l6=[],
    )
    assert resultado["totales_diagnosticos"] == [{
        "A": "017-CANJE RECIBIDO TARJETA CREDITO PAGOS",
        "B": 4,
        "C": "0.0000",
        "D": "11747250.0000",
        "nulos_total": 0,
        "nulos_interc": 0,
        "archivos": [5046],
        "insumos": ["CANT"],
    }]
