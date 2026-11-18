from copy import deepcopy
import pytest
from app.services.fase2.contrato_maestro_inc39 import COLUMNAS
from app.services.fase2.integracion_redeban_inc64 import adjuntar_diagnostico


def base():
    return {"id_jornada": 5066, "columnas": list(COLUMNAS),
            "filas": [{"cuenta": "299095302", "diferencia": None}],
            "indicadores": {"cruces": 0}, "certificado": False,
            "diagnostico_pmd_inc59": {"certificado": False}}


def proyeccion():
    return {"id_jornada": 5066, "version_catalogo": "sha256-prueba",
            "certificado": False, "cantidad_filas": 2, "filas": [
                {"id_jornada": 5066, "version_catalogo": "sha256-prueba",
                 "fila_excel": 8, "codigo_operacion": "1.1.1.10.102",
                 "categoria": "A", "cuenta_contable": "196095001828",
                 "estado": "CALCULO_DIAGNOSTICO", "neto_diagnostico": "80",
                 "certificado": False},
                {"id_jornada": 5066, "version_catalogo": "sha256-prueba",
                 "fila_excel": 1371, "codigo_operacion": "1.1.1.8.5008",
                 "categoria": "A", "estado": "FORMULA_EXCEPCIONAL_PENDIENTE",
                 "neto_diagnostico": None, "certificado": False}]}


def test_conserva_maestro_y_no_muta():
    original = base(); antes = deepcopy(original)
    salida = adjuntar_diagnostico(original, proyeccion())
    assert original == antes
    for campo in ("columnas", "filas", "indicadores", "diagnostico_pmd_inc59"):
        assert salida[campo] == original[campo]
    assert salida["certificado"] is False
    assert salida["diagnostico_redeban_inc64"]["estados"] == {
        "CALCULO_DIAGNOSTICO": 1, "FORMULA_EXCEPCIONAL_PENDIENTE": 1}


def test_jornada_incompatible():
    p = proyeccion(); p["id_jornada"] = 1
    with pytest.raises(ValueError, match="Jornada"):
        adjuntar_diagnostico(base(), p)


def test_rechaza_certificacion():
    p = proyeccion(); p["filas"][0]["certificado"] = True
    with pytest.raises(ValueError):
        adjuntar_diagnostico(base(), p)


def test_rechaza_excepcion_con_neto():
    p = proyeccion(); p["filas"][1]["neto_diagnostico"] = "1"
    with pytest.raises(ValueError):
        adjuntar_diagnostico(base(), p)


def test_rechaza_duplicado():
    p = proyeccion(); p["filas"][1]["fila_excel"] = 8
    with pytest.raises(ValueError):
        adjuntar_diagnostico(base(), p)


def test_rechaza_columnas_incorrectas():
    r = base(); r["columnas"] = ["otra"] * 11
    with pytest.raises(ValueError):
        adjuntar_diagnostico(r, proyeccion())


def test_rechaza_version_inconsistente():
    p = proyeccion(); p["filas"][0]["version_catalogo"] = "otra"
    with pytest.raises(ValueError):
        adjuntar_diagnostico(base(), p)
