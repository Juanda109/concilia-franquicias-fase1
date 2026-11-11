from app.services.fase2.clasificacion_depo_integral import clasificar


def test_cnb_010_no_se_clasifica_como_nacional():
    assert clasificar("02", None, "010", None) == "017-OP CNBS"


def test_cnb_011_no_se_clasifica_como_nacional():
    assert clasificar("02", None, "011", None) == "017-OP CNBS"


def test_cnb_012_no_se_clasifica_como_nacional():
    assert clasificar("02", None, "012", None) == "017-OP CNBS"


def test_cnb_110_no_se_clasifica_como_nacional():
    assert clasificar("02", None, "110", None) == "017-OP CNBS"


def test_cnb_111_no_se_clasifica_como_nacional():
    assert clasificar("02", None, "111", None) == "017-OP CNBS"


def test_cnb_112_no_se_clasifica_como_nacional():
    assert clasificar("02", None, "112", None) == "017-OP CNBS"


def test_movimiento_06_oficina_distinta_0090_es_nacional():
    assert (
        clasificar("06", "0017", None, None)
        == "017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS"
    )


def test_movimiento_06_oficina_0090_es_internacional():
    assert (
        clasificar("06", "0090", None, None)
        == "017-VR. DEPOSITOS ELECTRONICOS INTERNACIONAL CONSIGNADOS"
    )


def test_movimiento_06_amex_internacional_es_internacional():
    assert (
        clasificar("06", "0017", None, "AMEX INTERNACIONAL")
        == "017-VR. DEPOSITOS ELECTRONICOS INTERNACIONAL CONSIGNADOS"
    )


def test_movimiento_06_amex_nacional_es_nacional():
    assert (
        clasificar("06", "0017", None, "AMEX NACIONAL")
        == "017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS"
    )


def test_movimiento_05_es_control():
    assert clasificar("05", "0017", None, None) == "CONTROL_RESUMEN_EXCLUIDO"


def test_movimiento_02_oficina_distinta_0090_es_retiro_atm_nacional():
    assert (
        clasificar("02", "0017", None, None)
        == "017-VR. RET ATMs ADQUIRIENTES EN BBV NAL"
    )


def test_sin_regla_devuelve_sin_clasificacion():
    assert clasificar("99", "0017", None, None) == "SIN_CLASIFICACION_AU"

from app.services.fase2.cierre_credibanco_v67 import agrupar_depo


def test_agrupar_depo_tipo_06_oficina_0017_asigna_cuenta_nacional():
    filas = [{
        "id_archivo": 6001,
        "tipo_movimiento": "06",
        "cod_oficina": "0017",
        "indicador_cnb": None,
        "indicador_cash_back": None,
        "amex_nacional": None,
        "cantidad": 2,
        "valor_total_crudo": "1000000",
        "valor_intercambio_crudo": "10000",
        "valor_intercambio_2_crudo": None,
        "tasa_intercambio_cruda": "1000000",
    }]

    salida = agrupar_depo(filas, {6001})

    assert len(salida) == 1
    assert salida[0]["concepto"] == (
        "017-VR. DEPOSITOS ELECTRONICOS NAL CONSIGNADOS"
    )
    assert salida[0]["cuenta_host_candidata"] == "196095001838"
    assert salida[0]["cantidad"] == 2
    assert salida[0]["valor_total_crudo"] == "1000000"
    assert salida[0]["valor_intercambio_crudo"] == "10000"
    assert salida[0]["estado"] == "PENDIENTE_ESCALA_SIGNO_Y_FUENTE_HOST"
    assert salida[0]["certificado"] is False


def test_agrupar_depo_tipo_06_oficina_0090_asigna_cuenta_internacional():
    filas = [{
        "id_archivo": 6002,
        "tipo_movimiento": "06",
        "cod_oficina": "0090",
        "indicador_cnb": None,
        "indicador_cash_back": None,
        "amex_nacional": None,
        "indicador_cash_back": None,
        "cantidad": 3,
        "valor_total_crudo": "2000000",
        "valor_intercambio_crudo": "20000",
        "valor_intercambio_2_crudo": None,
        "tasa_intercambio_cruda": "2000000",
    }]

    salida = agrupar_depo(filas, {6002})

    assert len(salida) == 1
    assert salida[0]["concepto"] == (
        "017-VR. DEPOSITOS ELECTRONICOS INTERNACIONAL CONSIGNADOS"
    )
    assert salida[0]["cuenta_host_candidata"] == "196095001839"
    assert salida[0]["cantidad"] == 3
    assert salida[0]["valor_total_crudo"] == "2000000"
    assert salida[0]["valor_intercambio_crudo"] == "20000"
    assert salida[0]["estado"] == "PENDIENTE_ESCALA_SIGNO_Y_FUENTE_HOST"
    assert salida[0]["certificado"] is False

def test_agrupar_depo_calcula_tasa_intercambio_para_tipo_02():
    filas = [{
        "id_archivo": 7004,
        "tipo_movimiento": "02",
        "cod_oficina": "0017",
        "indicador_cnb": "010",
        "indicador_cash_back": "010",
        "amex_nacional": None,
        "cantidad": 4,
        "valor_total_crudo": "11849676",
        "valor_intercambio_crudo": "102426",
        "valor_intercambio_2_crudo": None,
        "tasa_intercambio_cruda": "11849676.0000",
    }]

    salida = agrupar_depo(filas, {7004})

    assert len(salida) == 1
    assert salida[0]["concepto"] == "017-OP CNBS"
    assert salida[0]["tasa_intercambio_calculada_cruda"] == "11747250"
    assert salida[0]["concepto_tii"] == (
        "017-ASC -CANJE ENVI. ADQUIRENTE- "
        "BINES NAL T. I.-MP TII NAL"
    )
    assert salida[0]["concepto_tii_amex"] is None
    assert salida[0]["concepto_comision_atm"] == (
        "017-VR. COMISIONES ADQ EN ATMs BBV $3.088"
    )
    assert salida[0]["cuenta_host_candidata"] is None
    assert salida[0]["certificado"] is False


def test_agrupar_depo_tipo_26_invierte_tasa_intercambio():
    filas = [{
        "id_archivo": 7005,
        "tipo_movimiento": "26",
        "cod_oficina": "0017",
        "indicador_cnb": None,
        "indicador_cash_back": None,
        "amex_nacional": None,
        "cantidad": 1,
        "valor_total_crudo": "100000",
        "valor_intercambio_crudo": "10000",
        "valor_intercambio_2_crudo": None,
        "tasa_intercambio_cruda": "90000",
    }]

    salida = agrupar_depo(filas, {7005})

    assert len(salida) == 1
    assert salida[0]["tasa_intercambio_calculada_cruda"] == "-90000"
    assert salida[0]["concepto_comision_atm"] is None


def test_agrupar_depo_tipo_06_oficina_0090_genera_tii_internacional():
    filas = [{
        "id_archivo": 7006,
        "tipo_movimiento": "06",
        "cod_oficina": "0090",
        "indicador_cnb": None,
        "indicador_cash_back": None,
        "amex_nacional": None,
        "cantidad": 1,
        "valor_total_crudo": "100000",
        "valor_intercambio_crudo": "10000",
        "valor_intercambio_2_crudo": None,
        "tasa_intercambio_cruda": "90000",
    }]

    salida = agrupar_depo(filas, {7006})

    assert len(salida) == 1
    assert salida[0]["concepto"] == (
        "017-VR. DEPOSITOS ELECTRONICOS INTERNACIONAL CONSIGNADOS"
    )
    assert salida[0]["concepto_tii"] == (
        "017-TASA INTERBAN TD-TC D.E. VISA TII INTER"
    )
    assert salida[0]["concepto_tii_amex"] is None

from app.services.fase2.reporte_credibanco_productivo import _derivados_depo


def test_reporte_productivo_agrega_derivados_depo():
    grupos = [
        {
            "tasa_intercambio_calculada_cruda": "11747250",
            "concepto_tii": (
                "017-ASC -CANJE ENVI. ADQUIRENTE- "
                "BINES NAL T. I.-MP TII NAL"
            ),
            "concepto_tii_amex": None,
            "concepto_comision_atm": (
                "017-VR. COMISIONES ADQ EN ATMs BBV $3.088"
            ),
        },
        {
            "tasa_intercambio_calculada_cruda": "100",
            "concepto_tii": (
                "017-ASC -CANJE ENVI. ADQUIRENTE- "
                "BINES NAL T. I.-MP TII NAL"
            ),
            "concepto_tii_amex": "017-TII AMEX INTERNACIONAL",
            "concepto_comision_atm": None,
        },
    ]

    salida = _derivados_depo(grupos)

    assert salida["tasa_intercambio_calculada_cruda"] == "11747350"
    assert salida["conceptos_tii"] == [
        "017-ASC -CANJE ENVI. ADQUIRENTE- "
        "BINES NAL T. I.-MP TII NAL"
    ]
    assert salida["conceptos_tii_amex"] == [
        "017-TII AMEX INTERNACIONAL"
    ]
    assert salida["conceptos_comision_atm"] == [
        "017-VR. COMISIONES ADQ EN ATMs BBV $3.088"
    ]
    assert salida["certificado"] is False
