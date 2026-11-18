"""INC60: proyeccion diagnostica ESTRUCTURA por jornada."""

from app.services.fase2.excepciones_estructura_inc60 import clasificar
from app.services.fase2.formulas_redeban_inc60 import proyectar


def proyectar_estructura(catalogo, filas_pmd, id_jornada):
    if type(id_jornada) is not int or id_jornada <= 0:
        raise ValueError("Jornada invalida")

    if not isinstance(catalogo, dict):
        raise ValueError("Catalogo invalido")

    version = catalogo.get("version_catalogo")

    if not version:
        raise ValueError("Version de catalogo requerida")

    resultados = []

    for fila in catalogo["registros"]:
        clasificacion = clasificar(fila)

        resultado = {
            "id_jornada": id_jornada,
            "version_catalogo": version,
            "fila_excel": fila["fila_excel"],
            "codigo_operacion": fila["codigo_operacion"],
            "categoria": fila["categoria"],
            "cuenta_contable": fila["cuenta_contable"],
            "centro_costos": fila["centro_costos"],
            "referencia_contable_formula":
                fila["referencia_contable_formula"],
            "clasificacion": clasificacion["estado"],
            "neto_diagnostico": None,
            "estado": clasificacion["estado"],
            "certificado": False,
        }

        if clasificacion["estado"] == "FORMULA_ESTANDAR":
            calculo = proyectar(
                filas_pmd,
                fila["codigo_operacion"],
                fila["categoria"],
            )

            resultado["neto_diagnostico"] = calculo[
                "neto_diagnostico"
            ]
            resultado["estado"] = calculo["estado"]
            resultado["calculo"] = calculo

        resultados.append(resultado)

    return {
        "id_jornada": id_jornada,
        "version_catalogo": version,
        "cantidad_filas": len(resultados),
        "filas": resultados,
        "certificado": False,
        "estado": "DIAGNOSTICO_NO_HOMOLOGADO",
    }
