from app.services.fase2.alcance_manuales_inc66 import (
    clasificar_partidas_manuales,
)


def test_seis_partidas_fuera_alcance():
    cuentas = [
        "514005180",
        "196095001035",
        "196095001035",
        "196095001035",
        "196095001035",
        "196095001035",
    ]

    filas = [
        {
            "fila_excel": 3246 + indice,
            "cuenta_contable": cuenta,
            "estado": "PARTIDA_MANUAL_NO_HOMOLOGADA",
            "neto_diagnostico": None,
            "certificado": False,
        }
        for indice, cuenta in enumerate(cuentas)
    ]

    proyeccion = {
        "id_jornada": 6466,
        "version_catalogo": "prueba",
        "filas": filas,
        "cantidad_filas": 6,
        "certificado": False,
    }

    resultado = clasificar_partidas_manuales(proyeccion)

    diagnostico = resultado["diagnostico_alcance_inc66"]

    assert diagnostico["cantidad_partidas"] == 6
    assert diagnostico["fuera_alcance"] == 6
    assert diagnostico["en_alcance"] == 0

    assert all(
        fila["estado"] == "PARTIDA_MANUAL_NO_HOMOLOGADA"
        for fila in resultado["filas"]
    )

    assert all(
        fila["neto_diagnostico"] is None
        for fila in resultado["filas"]
    )

    assert resultado["certificado"] is False


def test_rechaza_proyeccion_certificada():
    try:
        clasificar_partidas_manuales({
            "filas": [],
            "cantidad_filas": 0,
            "certificado": True,
        })
    except ValueError:
        pass
    else:
        raise AssertionError("Debio rechazar certificacion")


def test_no_modifica_original():
    original = {
        "filas": [{
            "fila_excel": 3246,
            "cuenta_contable": "514005180",
            "estado": "PARTIDA_MANUAL_NO_HOMOLOGADA",
            "neto_diagnostico": None,
            "certificado": False,
        }],
        "cantidad_filas": 1,
        "certificado": False,
    }

    clasificar_partidas_manuales(original)

    assert "estado_alcance" not in original["filas"][0]
