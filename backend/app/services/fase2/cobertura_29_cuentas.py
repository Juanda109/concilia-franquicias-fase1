"""Cobertura de las 29 cuentas contables de Concilia V1."""

from app.services.catalogo_cuentas_host import cargar_cuentas_host


def construir_cobertura_cuentas(movimientos):
    catalogo = cargar_cuentas_host()

    resultado = {
        cuenta: {
            "cuenta": cuenta,
            "centro": "0017",
            "descripcion": datos["descripcion_cuadre"],
            "regla_consulta": datos["regla_consulta"],
            "estado": "SIN_MOVIMIENTOS",
            "movimientos": [],
        }
        for cuenta, datos in catalogo.items()
    }

    for movimiento in movimientos:
        cuenta = str(movimiento.get("cuenta") or "").strip()
        centro = str(movimiento.get("centro") or "").strip()

        if cuenta not in resultado:
            continue

        # CONCILIA_CENTRO_17_FUNCIONAL_V1
        if centro not in ("", "17", "0017"):
            continue

        evidencia = dict(movimiento)
        evidencia["centro_origen"] = movimiento.get("centro")
        evidencia["centro_funcional"] = "0017"
        evidencia["centro_inferido"] = centro == ""

        resultado[cuenta]["movimientos"].append(evidencia)
        resultado[cuenta]["estado"] = "CON_MOVIMIENTOS"


    # CONCILIA_CORRESPONDENCIA_FRANQUICIAS_V1
    from app.services.fase2.homologacion_franquicias import cargar_homologaciones

    homologaciones = cargar_homologaciones()

    for cuenta, fila in resultado.items():
        regla = homologaciones[cuenta]
        fila["franquicia_relacionada"] = regla["franquicia_relacionada"]
        fila["proceso_cuadre"] = regla["proceso_cuadre"]
        fila["evidencia_homologacion"] = regla["evidencia"]
        fila["certeza_homologacion"] = regla["certeza"]
        fila["estado_homologacion"] = regla["estado_homologacion"]

    return list(resultado.values())
