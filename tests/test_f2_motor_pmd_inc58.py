from decimal import Decimal

from app.services.fase2.motor_pmd_inc58 import (
    buscar_nivel,
    contar_codigo,
    prefijo_codigo,
    diagnosticar,
    decimal_exacto,
)

import pytest


def muestra():
    return [
        {
            "NIVEL": "1.1.1",
            "DEBITO_VALOR": Decimal("100.25"),
            "CREDITO_VALOR": Decimal("20.10"),
            "numero_linea": 3,
            "ES_CONTROL": False,
        },
        {
            "NIVEL": "1.1.2",
            "DEBITO_VALOR": Decimal("200.00"),
            "CREDITO_VALOR": Decimal("30.00"),
            "numero_linea": 4,
            "ES_CONTROL": False,
        },
    ]


def test_busqueda_exacta():
    resultado = buscar_nivel(
        muestra(), "1.1.1", "DEBITO_VALOR"
    )

    assert resultado["estado"] == "ENCONTRADO"
    assert resultado["valor"] == "100.25"
    assert resultado["lineas_origen"] == [3]


def test_sin_coincidencia():
    resultado = buscar_nivel(
        muestra(), "9.9", "DEBITO_VALOR"
    )

    assert resultado["estado"] == "SIN_COINCIDENCIA"
    assert resultado["valor"] is None


def test_duplicados():
    filas = muestra()
    filas.append(dict(filas[0]))

    resultado = buscar_nivel(
        filas, "1.1.1", "DEBITO_VALOR"
    )

    assert resultado["estado"] == "NIVEL_DUPLICADO"
    assert resultado["valor"] is None


def test_prefijos():
    assert prefijo_codigo("299095302", 3) == "299"
    assert prefijo_codigo("299095302", 5) == "29909"


def test_countif():
    assert contar_codigo(
        ["001", "002", "001"], "001"
    ) == 2


def test_precision():
    assert decimal_exacto("123.45") == Decimal("123.45")

    with pytest.raises(ValueError):
        decimal_exacto(float("nan"))


def test_no_certificacion():
    resultado = diagnosticar(muestra(), 5683)

    assert resultado["certificado"] is False
    assert resultado["valor_franquicia_certificado"] is None
    assert resultado["total_host_homologado"] is None
    assert resultado["diferencia_certificada"] is None


def test_controles_separados():
    filas = muestra()
    filas.append({
        "NIVEL": "1",
        "ES_CONTROL": True,
    })

    resultado = diagnosticar(filas, 5683)

    assert resultado["cantidad_registros"] == 3
    assert resultado["cantidad_controles"] == 1


def test_rechaza_medida_desconocida():
    with pytest.raises(ValueError):
        buscar_nivel(muestra(), "1.1.1", "CUENTA_CONTABLE")


def test_busqueda_excluye_control():
    filas = muestra()

    filas.insert(0, {
        "NIVEL": "1.1.1",
        "DEBITO_VALOR": Decimal("999999.00"),
        "numero_linea": 2,
        "ES_CONTROL": True,
    })

    resultado = buscar_nivel(
        filas, "1.1.1", "DEBITO_VALOR"
    )

    assert resultado["estado"] == "ENCONTRADO"
    assert resultado["valor"] == "100.25"
    assert resultado["lineas_origen"] == [3]


def test_solo_control_no_es_coincidencia():
    filas = [{
        "NIVEL": "1.1.1",
        "DEBITO_VALOR": Decimal("100.00"),
        "numero_linea": 2,
        "ES_CONTROL": True,
    }]

    resultado = buscar_nivel(
        filas, "1.1.1", "DEBITO_VALOR"
    )

    assert resultado["estado"] == "SIN_COINCIDENCIA"
    assert resultado["valor"] is None


def test_indices_vlookup():
    from app.services.fase2.motor_pmd_inc58 import buscar_indice_plantilla

    fila = {
        "NIVEL": "1.1",
        "ES_CONTROL": False,
        "numero_linea": 3,
        "DEBITO_CANTIDAD": Decimal("1"),
        "DEBITO_VALOR": Decimal("11747250"),
        "DEBITO_NETO": Decimal("11747250"),
        "CREDITO_CANTIDAD": Decimal("0"),
        "CREDITO_VALOR": Decimal("0"),
        "CREDITO_NETO": Decimal("0"),
        "TOTAL": Decimal("11747250"),
    }

    esperados = {
        2: "1",
        3: "11747250",
        6: "11747250",
        7: "0",
        8: "0",
        11: "0",
        12: "11747250",
    }

    for indice, valor in esperados.items():
        resultado = buscar_indice_plantilla([fila], "1.1", indice)

        assert resultado["estado"] == "ENCONTRADO"
        assert resultado["valor"] == valor
        assert resultado["certificado"] is False


def test_vlookup_sin_coincidencia():
    from app.services.fase2.motor_pmd_inc58 import buscar_indice_plantilla

    resultado = buscar_indice_plantilla([], "1.1", 3)

    assert resultado["estado"] == "SIN_COINCIDENCIA"
    assert resultado["valor"] is None
    assert resultado["certificado"] is False


def test_vlookup_rechaza_indice_desconocido():
    from app.services.fase2.motor_pmd_inc58 import buscar_indice_plantilla

    with pytest.raises(ValueError):
        buscar_indice_plantilla(muestra(), "1.1.1", 99)


def test_vlookup_no_utiliza_controles():
    from app.services.fase2.motor_pmd_inc58 import buscar_indice_plantilla

    filas = [{
        "NIVEL": "1.1",
        "ES_CONTROL": True,
        "numero_linea": 2,
        "DEBITO_VALOR": Decimal("999999"),
    }]

    resultado = buscar_indice_plantilla(filas, "1.1", 3)

    assert resultado["estado"] == "SIN_COINCIDENCIA"
    assert resultado["valor"] is None


def test_neto_con_credito():
    from app.services.fase2.motor_pmd_inc58 import calcular_neto_estructura

    filas = [{
        "NIVEL": "1.1",
        "ES_CONTROL": False,
        "numero_linea": 3,
        "DEBITO_VALOR": Decimal("100.25"),
        "CREDITO_VALOR": Decimal("30.10"),
    }]

    r = calcular_neto_estructura(filas, "1.1")

    assert r["neto_diagnostico"] == "70.15"
    assert r["signo_credito"] == -1
    assert r["certificado"] is False


def test_neto_sin_nivel():
    from app.services.fase2.motor_pmd_inc58 import calcular_neto_estructura

    r = calcular_neto_estructura([], "9.9")

    assert r["estado"] == "OPERANDOS_NO_RESUELTOS"
    assert r["neto_diagnostico"] is None


def test_neto_con_duplicados():
    from app.services.fase2.motor_pmd_inc58 import calcular_neto_estructura

    filas = muestra()
    filas.append(dict(filas[0]))

    r = calcular_neto_estructura(filas, "1.1.1")

    assert r["estado"] == "OPERANDOS_NO_RESUELTOS"
    assert r["neto_diagnostico"] is None


def test_neto_con_valor_nulo():
    from app.services.fase2.motor_pmd_inc58 import calcular_neto_estructura

    filas = [{
        "NIVEL": "1.1",
        "ES_CONTROL": False,
        "numero_linea": 3,
        "DEBITO_VALOR": None,
        "CREDITO_VALOR": Decimal("10"),
    }]

    r = calcular_neto_estructura(filas, "1.1")

    assert r["estado"] == "VALOR_AUSENTE"
    assert r["neto_diagnostico"] is None


def test_validador_medidas():
    from app.services.fase2.motor_pmd_inc58 import diagnosticar_validador

    filas = [{
        "NIVEL": "1.1",
        "ES_CONTROL": False,
        "numero_linea": 3,
        "DEBITO_NETO": Decimal("100.25"),
        "CREDITO_NETO": Decimal("30.10"),
        "TOTAL": Decimal("70.15"),
    }]

    r = diagnosticar_validador(filas, "1.1")

    assert r["estado"] == "MEDIDAS_RECUPERADAS"
    assert r["medidas"]["debito_neto"]["valor"] == "100.25"
    assert r["medidas"]["credito_neto"]["valor"] == "30.10"
    assert r["medidas"]["total_pmd"]["valor"] == "70.15"
    assert r["control_f4_j4"] is None
    assert r["certificado"] is False


def test_validador_sin_nivel():
    from app.services.fase2.motor_pmd_inc58 import diagnosticar_validador

    r = diagnosticar_validador([], "9.9")

    assert r["estado"] == "MEDIDAS_INCOMPLETAS"
    assert r["control_f4_j4"] is None


def test_validador_duplicados():
    from app.services.fase2.motor_pmd_inc58 import diagnosticar_validador

    filas = [{
        "NIVEL": "1.1",
        "ES_CONTROL": False,
        "numero_linea": 3,
        "DEBITO_NETO": Decimal("100"),
        "CREDITO_NETO": Decimal("20"),
        "TOTAL": Decimal("80"),
    }]

    filas.append(dict(filas[0]))

    r = diagnosticar_validador(filas, "1.1")

    assert r["estado"] == "MEDIDAS_INCOMPLETAS"
    assert r["medidas"]["total_pmd"]["estado"] == "NIVEL_DUPLICADO"
    assert r["certificado"] is False


def test_control_validador_cuadra():
    from app.services.fase2.motor_pmd_inc58 import calcular_control_validador

    filas = [{
        "NIVEL": "1.1",
        "ES_CONTROL": False,
        "numero_linea": 3,
        "TOTAL": Decimal("100.25"),
    }]

    r = calcular_control_validador(
        filas, "1.1", Decimal("-100.25"), "ESTRUCTURA!F5"
    )

    assert r["estado"] == "CONTROL_DIAGNOSTICO"
    assert Decimal(r["control_diagnostico"]) == Decimal("0")
    assert r["certificado"] is False


def test_control_validador_diferencia():
    from app.services.fase2.motor_pmd_inc58 import calcular_control_validador

    filas = [{
        "NIVEL": "1.1",
        "ES_CONTROL": False,
        "numero_linea": 3,
        "TOTAL": Decimal("100"),
    }]

    r = calcular_control_validador(
        filas, "1.1", Decimal("-90"), "ESTRUCTURA!F5"
    )

    assert Decimal(r["control_diagnostico"]) == Decimal("10")
    assert r["diferencia_certificada"] is None


def test_control_validador_sin_estructura():
    from app.services.fase2.motor_pmd_inc58 import calcular_control_validador

    r = calcular_control_validador(
        [], "1.1", None, "ESTRUCTURA!F5"
    )

    assert r["estado"] == "OPERANDOS_NO_RESUELTOS"
    assert r["control_diagnostico"] is None


def test_control_validador_nivel_inexistente():
    from app.services.fase2.motor_pmd_inc58 import calcular_control_validador

    r = calcular_control_validador(
        [], "9.9", Decimal("100"), "ESTRUCTURA!F5"
    )

    assert r["estado"] == "OPERANDOS_NO_RESUELTOS"
    assert r["control_diagnostico"] is None


def test_control_validador_referencia_obligatoria():
    from app.services.fase2.motor_pmd_inc58 import calcular_control_validador

    with pytest.raises(ValueError):
        calcular_control_validador(
            [], "1.1", Decimal("100"), ""
        )


def test_estructura2_credito_no_cero():
    from app.services.fase2.motor_pmd_inc58 import diagnosticar_estructura_2

    filas = [{
        "NIVEL": "3.1.2.10.110",
        "ES_CONTROL": False,
        "numero_linea": 3,
        "DEBITO_VALOR": Decimal("100.25"),
        "CREDITO_VALOR": Decimal("30.10"),
        "DEBITO_CANTIDAD": Decimal("2"),
        "CREDITO_CANTIDAD": Decimal("1"),
    }]

    r = diagnosticar_estructura_2(filas, "3.1.2.10.110")

    assert r["prefijo_3"] == "3.1"
    assert r["prefijo_5"] == "3.1.2"
    assert Decimal(r["credito_firmado"]) == Decimal("-30.10")
    assert Decimal(r["neto_diagnostico"]) == Decimal("70.15")
    assert r["estado"] == "CALCULO_DIAGNOSTICO"
    assert r["certificado"] is False


def test_estructura2_sin_codigo():
    from app.services.fase2.motor_pmd_inc58 import diagnosticar_estructura_2

    r = diagnosticar_estructura_2([], "3.1.2.10.110")

    assert r["estado"] == "OPERANDOS_NO_RESUELTOS"
    assert r["neto_diagnostico"] is None


def test_estructura2_duplicados():
    from app.services.fase2.motor_pmd_inc58 import diagnosticar_estructura_2

    fila = {
        "NIVEL": "3.1.2.10.110",
        "ES_CONTROL": False,
        "numero_linea": 3,
        "DEBITO_VALOR": Decimal("100"),
        "CREDITO_VALOR": Decimal("20"),
        "DEBITO_CANTIDAD": Decimal("2"),
        "CREDITO_CANTIDAD": Decimal("1"),
    }

    r = diagnosticar_estructura_2(
        [fila, dict(fila)], "3.1.2.10.110"
    )

    assert r["estado"] == "OPERANDOS_NO_RESUELTOS"
    assert r["neto_diagnostico"] is None


def test_estructura2_valor_nulo():
    from app.services.fase2.motor_pmd_inc58 import diagnosticar_estructura_2

    filas = [{
        "NIVEL": "3.1.2.10.110",
        "ES_CONTROL": False,
        "numero_linea": 3,
        "DEBITO_VALOR": None,
        "CREDITO_VALOR": Decimal("20"),
        "DEBITO_CANTIDAD": Decimal("2"),
        "CREDITO_CANTIDAD": Decimal("1"),
    }]

    r = diagnosticar_estructura_2(filas, "3.1.2.10.110")

    assert r["estado"] == "VALOR_AUSENTE"
    assert r["neto_diagnostico"] is None


def test_iferror_sin_coincidencia():
    from app.services.fase2.motor_pmd_inc58 import buscar_indice_iferror

    r = buscar_indice_iferror([], "1.1", 3)

    assert r["estado"] == "CERO_POR_AUSENCIA"
    assert r["estado_original"] == "SIN_COINCIDENCIA"
    assert r["valor"] == "0"
    assert r["cero_por_ausencia"] is True
    assert r["certificado"] is False


def test_iferror_coincidencia_real():
    from app.services.fase2.motor_pmd_inc58 import buscar_indice_iferror

    r = buscar_indice_iferror(muestra(), "1.1.1", 3)

    assert r["estado"] == "ENCONTRADO"
    assert r["valor"] == "100.25"
    assert r["cero_por_ausencia"] is False


def test_iferror_duplicados_bloqueados():
    from app.services.fase2.motor_pmd_inc58 import buscar_indice_iferror

    filas = muestra()
    filas.append(dict(filas[0]))

    r = buscar_indice_iferror(filas, "1.1.1", 3)

    assert r["estado"] == "NIVEL_DUPLICADO"
    assert r["valor"] is None
    assert r["cero_por_ausencia"] is False


def test_iferror_valor_nulo():
    from app.services.fase2.motor_pmd_inc58 import buscar_indice_iferror

    filas = [{
        "NIVEL": "1.1",
        "ES_CONTROL": False,
        "numero_linea": 3,
        "DEBITO_VALOR": None,
    }]

    r = buscar_indice_iferror(filas, "1.1", 3)

    assert r["estado"] == "ENCONTRADO"
    assert r["valor"] is None
    assert r["cero_por_ausencia"] is False
