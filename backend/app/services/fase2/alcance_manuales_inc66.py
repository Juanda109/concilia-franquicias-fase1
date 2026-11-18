"""INC66: clasificación de alcance de partidas manuales Redeban."""

from copy import deepcopy

from app.services.catalogo_cuentas_host import cargar_cuentas_host

ESTADO_MANUAL = "PARTIDA_MANUAL_NO_HOMOLOGADA"


def clasificar_partidas_manuales(proyeccion):
    """Clasifica sin eliminar filas ni alterar importes."""
    if proyeccion.get("certificado") is not False:
        raise ValueError("Proyeccion certificada no permitida")

    filas = proyeccion["filas"]

    if proyeccion.get("cantidad_filas") != len(filas):
        raise ValueError("Cantidad de filas inconsistente")

    catalogo = cargar_cuentas_host()
    resultado = deepcopy(proyeccion)

    clasificadas = []

    for fila in resultado["filas"]:
        if fila.get("estado") != ESTADO_MANUAL:
            continue

        cuenta = str(fila.get("cuenta_contable") or "").strip()

        en_alcance = cuenta in catalogo

        fila["cuenta_en_alcance"] = en_alcance
        fila["estado_alcance"] = (
            "CUENTA_EN_ALCANCE"
            if en_alcance
            else "CUENTA_FUERA_ALCANCE"
        )

        fila["certificado"] = False

        clasificadas.append({
            "fila_excel": fila.get("fila_excel"),
            "cuenta_contable": cuenta,
            "estado_alcance": fila["estado_alcance"],
        })

    resultado["diagnostico_alcance_inc66"] = {
        "cantidad_partidas": len(clasificadas),
        "en_alcance": sum(
            x["estado_alcance"] == "CUENTA_EN_ALCANCE"
            for x in clasificadas
        ),
        "fuera_alcance": sum(
            x["estado_alcance"] == "CUENTA_FUERA_ALCANCE"
            for x in clasificadas
        ),
        "detalle": clasificadas,
        "certificado": False,
    }

    resultado["certificado"] = False
    return resultado
