from decimal import Decimal

import pytest

from app.services.fase2.proyeccion_estructura_inc60 import (
    proyectar_estructura,
)


def regla(numero, codigo, tipo, db, cr):
    return {
        "fila_excel": numero,
        "codigo_operacion": codigo,
        "categoria": tipo,
        "tipo_operacion": tipo,
        "cuenta_contable": "196095001828",
        "centro_costos": 17,
        "referencia_contable_formula": "=+$M$2",
        "debito_formula":
            f"=IFERROR(VLOOKUP(F{numero},PMD!$C:$N,{db},0),0)",
        "credito_formula":
            f"=IFERROR(VLOOKUP(F{numero},PMD!$C:$N,{cr},0),0)*-1",
    }


def catalogo():
    return {
        "version_catalogo": "PRUEBA_INC60",
        "registros": [
            regla(8, "1.1.1.10.102", "A", 3, 8),
            regla(1249, "1.1.1.10.102", "B", 4, 9),
            regla(2285, "1.1.1.10.102", "C", 5, 10),
            regla(1371, "1.1.1.8.5008", "A", 4, 9),
            {
                **regla(3246, "N/A", "C", 5, 10),
                "tipo_operacion": "CANCELACIÓN PARTIDA BAN. REP",
                "debito_formula": 1680713.98,
                "credito_formula": None,
            },
        ],
    }


def filas_pmd():
    return [{
        "NIVEL": "1.1.1.10.102",
        "ES_CONTROL": False,
        "numero_linea": 3,
        "DEBITO_VALOR": Decimal("100"),
        "CREDITO_VALOR": Decimal("20"),
        "DEBITO_COMISION_INTERCAMBIO": Decimal("10"),
        "CREDITO_COMISION_INTERCAMBIO": Decimal("3"),
        "DEBITO_COMISION_ADMINISTRATIVA": Decimal("5"),
        "CREDITO_COMISION_ADMINISTRATIVA": Decimal("2"),
    }]


def test_proyeccion_abc():
    resultado = proyectar_estructura(
        catalogo(), filas_pmd(), 5683
    )

    esperados = {
        8: Decimal("80"),
        1249: Decimal("7"),
        2285: Decimal("3"),
    }

    for fila in resultado["filas"]:
        if fila["fila_excel"] in esperados:
            assert Decimal(
                fila["neto_diagnostico"]
            ) == esperados[fila["fila_excel"]]

    assert resultado["certificado"] is False


def test_excepcion_bloqueada():
    resultado = proyectar_estructura(
        catalogo(), filas_pmd(), 5683
    )

    fila = next(
        f for f in resultado["filas"]
        if f["fila_excel"] == 1371
    )

    assert fila["estado"] == "FORMULA_EXCEPCIONAL_PENDIENTE"
    assert fila["neto_diagnostico"] is None


def test_partida_manual_bloqueada():
    resultado = proyectar_estructura(
        catalogo(), filas_pmd(), 5683
    )

    fila = next(
        f for f in resultado["filas"]
        if f["fila_excel"] == 3246
    )

    assert fila["estado"] == "PARTIDA_MANUAL_NO_HOMOLOGADA"
    assert fila["neto_diagnostico"] is None


@pytest.mark.parametrize("jornada", [0, -1, None, "5683", True])
def test_jornada_invalida(jornada):
    with pytest.raises(ValueError):
        proyectar_estructura(
            catalogo(), filas_pmd(), jornada
        )


def test_version_obligatoria():
    datos = catalogo()
    datos["version_catalogo"] = None

    with pytest.raises(ValueError):
        proyectar_estructura(datos, filas_pmd(), 5683)


def test_conserva_trazabilidad():
    resultado = proyectar_estructura(
        catalogo(), filas_pmd(), 5683
    )

    fila = resultado["filas"][0]

    assert fila["id_jornada"] == 5683
    assert fila["version_catalogo"] == "PRUEBA_INC60"
    assert fila["fila_excel"] == 8
    assert fila["cuenta_contable"] == "196095001828"
    assert fila["certificado"] is False
