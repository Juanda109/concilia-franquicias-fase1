"""INC64: adjunta diagnostico Redeban validado al maestro INC59.

No consulta plantillas locales ni modifica columnas, filas o indicadores.
"""
from collections import Counter
from copy import deepcopy

from app.services.fase2.contrato_maestro_inc39 import COLUMNAS

ESTADOS = frozenset({
    "CALCULO_DIAGNOSTICO", "OPERANDOS_NO_RESUELTOS",
    "FORMULA_EXCEPCIONAL_PENDIENTE", "PARTIDA_MANUAL_NO_HOMOLOGADA",
})


def adjuntar_diagnostico(reporte, proyeccion):
    """Agrega una proyeccion INC60 suministrada y vinculada a la jornada."""
    if not isinstance(reporte, dict) or reporte.get("certificado") is not False:
        raise ValueError("Reporte no diagnostico")
    if reporte.get("columnas") != list(COLUMNAS):
        raise ValueError("Contrato maestro distinto de INC39")
    jornada = reporte.get("id_jornada")
    if type(jornada) is not int or jornada <= 0:
        raise ValueError("Jornada invalida")
    if not isinstance(proyeccion, dict) or proyeccion.get("certificado") is not False:
        raise ValueError("Proyeccion no diagnostica")
    if proyeccion.get("id_jornada") != jornada:
        raise ValueError("Jornada PMD/Redeban diferente")
    version = proyeccion.get("version_catalogo")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Version catalogo requerida")
    filas = proyeccion.get("filas")
    if not isinstance(filas, list) or proyeccion.get("cantidad_filas") != len(filas):
        raise ValueError("Cantidad de filas inconsistente")
    if "diagnostico_redeban_inc64" in reporte:
        raise ValueError("Diagnostico INC64 ya incorporado")
    conteos = Counter()
    detalle = []
    numeros = set()
    for fila in filas:
        if not isinstance(fila, dict) or fila.get("certificado") is not False:
            raise ValueError("Fila no diagnostica")
        numero = fila.get("fila_excel")
        if type(numero) is not int or numero <= 0 or numero in numeros:
            raise ValueError("Fila Excel invalida o duplicada")
        numeros.add(numero)
        estado = fila.get("estado")
        if estado not in ESTADOS:
            raise ValueError("Estado INC60 desconocido")
        if fila.get("id_jornada") != jornada or fila.get("version_catalogo") != version:
            raise ValueError("Trazabilidad inconsistente")
        if estado != "CALCULO_DIAGNOSTICO" and fila.get("neto_diagnostico") is not None:
            raise ValueError("Excepcion con importe calculado")
        conteos[estado] += 1
        detalle.append({
            "fila_excel": numero,
            "codigo_operacion": fila.get("codigo_operacion"),
            "categoria": fila.get("categoria"),
            "cuenta_contable": fila.get("cuenta_contable"),
            "estado": estado,
            "neto_diagnostico": fila.get("neto_diagnostico"),
            "certificado": False,
        })
    salida = deepcopy(reporte)
    salida["diagnostico_redeban_inc64"] = {
        "id_jornada": jornada,
        "version_catalogo": version,
        "estado": "DIAGNOSTICO_NO_HOMOLOGADO",
        "cantidad_filas": len(filas),
        "estados": dict(sorted(conteos.items())),
        "detalle": detalle,
        "advertencia": "Sin homologacion Redeban-Host; no certifica conciliacion.",
        "certificado": False,
    }
    return salida
