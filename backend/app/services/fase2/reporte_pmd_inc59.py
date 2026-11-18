"""INC59: integra diagnostico PMD sin homologacion contable."""

from app.services.fase2.reporte_api_credibanco_inc47 import (
    consultar as consultar_base,
)
from app.services.fase2.repositorio_pmd_inc58 import leer_jornada
from app.services.fase2.motor_pmd_inc58 import (
    diagnosticar,
    diagnosticar_validador,
    calcular_neto_estructura,
)


def enriquecer(reporte, filas):
    if reporte.get("certificado") is not False:
        raise ValueError("Reporte certificado no permitido")

    if len(reporte.get("columnas", [])) != 11:
        raise ValueError("Contrato maestro invalido")

    jornada = reporte["id_jornada"]
    diagnostico = diagnosticar(filas, jornada)

    niveles = sorted({
        str(f["NIVEL"])
        for f in filas
        if not f.get("ES_CONTROL")
    })

    detalles = []

    for nivel in niveles:
        registros = [
            f for f in filas
            if not f.get("ES_CONTROL")
            and str(f["NIVEL"]) == nivel
        ]

        detalles.append({
            "nivel": nivel,
            "archivos_origen": sorted({
                f["id_archivo"] for f in registros
            }),
            "lineas_origen": [
                {
                    "id_archivo": f["id_archivo"],
                    "linea": f["numero_linea"],
                }
                for f in registros
            ],
            "medidas_validador": diagnosticar_validador(
                filas, nivel
            ),
            "neto_pmd_diagnostico": calcular_neto_estructura(
                filas, nivel
            ),
            "certificado": False,
        })

    respuesta = dict(reporte)

    respuesta["diagnostico_pmd_inc59"] = {
        **diagnostico,
        "archivos_origen": sorted({
            f["id_archivo"] for f in filas
        }),
        "detalle_niveles": detalles,
        "estado": "DIAGNOSTICO_NO_HOMOLOGADO",
        "advertencia": (
            "PMD diagnostico. No constituye "
            "conciliacion Redeban-Host."
        ),
    }

    respuesta["certificado"] = False

    return respuesta


def consultar(id_jornada):
    reporte = consultar_base(id_jornada)
    filas = leer_jornada(id_jornada)
    respuesta = enriquecer(reporte, filas)

    # INC64 solo se activa con un registro jornada/catalogo explicito.
    from app.services.fase2.vinculo_catalogo_inc64 import (
        resolver_vinculo, consultar_fecha_jornada,
    )
    import os

    # La plantilla es una fuente de REGLAS, no de importes.
    # Prioridad: vinculo explicito existente; alternativa: plantilla global
    # con SHA256 autorizado. Los importes siempre provienen del PMD de la jornada.
    from app.services.fase2.plantilla_reglas_redeban import resolver_plantilla_reglas

    if not (os.getenv("INC64_REGISTRO_CATALOGOS") or os.getenv("INC64_PLANTILLA_REGLAS")):
        return respuesta

    fecha = consultar_fecha_jornada(id_jornada)
    archivo = (resolver_vinculo(id_jornada, fecha)
               if os.getenv("INC64_REGISTRO_CATALOGOS") else None)
    if archivo is None:
        archivo = resolver_plantilla_reglas(id_jornada, fecha)
    if archivo is None:
        return respuesta

    from app.services.fase2.catalogo_estructura_inc60 import leer_catalogo
    from app.services.fase2.proyeccion_estructura_inc60 import proyectar_estructura
    from app.services.fase2.integracion_redeban_inc64 import adjuntar_diagnostico

    catalogo = leer_catalogo(archivo)
    proyeccion = proyectar_estructura(catalogo, filas, id_jornada)
    from app.services.fase2.integracion_excepcionales_inc65 import aplicar_excepcionales
    proyeccion = aplicar_excepcionales(proyeccion, filas)
    reporte_final = adjuntar_diagnostico(respuesta, proyeccion)

    from app.services.fase2.alcance_manuales_inc66 import (
        clasificar_partidas_manuales,
    )

    # Compatibilidad con respuestas simuladas de INC64.
    # INC66 solo clasifica cuando existe diagnostico Redeban.
    if "diagnostico_redeban_inc64" not in reporte_final:
        return reporte_final

    diagnostico = reporte_final["diagnostico_redeban_inc64"]

    proyeccion_alcance = {
        "id_jornada": id_jornada,
        "version_catalogo": diagnostico["version_catalogo"],
        "filas": diagnostico["detalle"],
        "cantidad_filas": diagnostico["cantidad_filas"],
        "certificado": False,
    }

    clasificada = clasificar_partidas_manuales(proyeccion_alcance)

    reporte_final["diagnostico_redeban_inc64"]["detalle"] = (
        clasificada["filas"]
    )
    reporte_final["diagnostico_alcance_inc66"] = (
        clasificada["diagnostico_alcance_inc66"]
    )
    reporte_final["certificado"] = False

    return reporte_final
