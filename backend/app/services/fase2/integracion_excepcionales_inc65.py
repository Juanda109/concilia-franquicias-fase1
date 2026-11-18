"""Integra cuatro excepciones INC65 en la proyeccion INC60, sin certificar."""
from copy import deepcopy

from app.services.fase2.excepcionales_redeban_inc65 import evaluar, INDICES

# PMD!C:N: C=Nivel, D:H=Debito, I:M=Credito, N=Total.
COLUMNAS_PMD = (
    "NIVEL", "DEBITO_CANTIDAD", "DEBITO_VALOR",
    "DEBITO_COMISION_INTERCAMBIO", "DEBITO_COMISION_ADMINISTRATIVA",
    "DEBITO_NETO", "CREDITO_CANTIDAD", "CREDITO_VALOR",
    "CREDITO_COMISION_INTERCAMBIO", "CREDITO_COMISION_ADMINISTRATIVA",
    "CREDITO_NETO", "TOTAL",
)


def aplicar_excepcionales(proyeccion, filas_pmd):
    """Devuelve copia; no cambia importes ni estados de partidas manuales."""
    if proyeccion.get("certificado") is not False:
        raise ValueError("Proyeccion debe ser no certificada")
    version = proyeccion["version_catalogo"]
    filas = proyeccion["filas"]
    if proyeccion.get("cantidad_filas") != len(filas):
        raise ValueError("Cantidad de filas inconsistente")
    secuencias = [
        [fila[c] for c in COLUMNAS_PMD]
        for fila in filas_pmd if not fila.get("ES_CONTROL")
    ]
    salida = deepcopy(proyeccion)
    resultados = []
    for fila in salida["filas"]:
        numero = fila.get("fila_excel")
        if numero not in INDICES:
            continue
        if fila.get("estado") != "FORMULA_EXCEPCIONAL_PENDIENTE":
            raise ValueError(f"Estado inesperado en fila {numero}")
        resultado = evaluar(
            numero, fila["codigo_operacion"], fila.get("cuenta_contable"),
            version, secuencias,
        )
        resultado["id_jornada"] = salida["id_jornada"]
        resultados.append(resultado)
        if resultado["estado"] == "CALCULO_DIAGNOSTICO_EXCEPCIONAL":
            fila["estado"] = "CALCULO_DIAGNOSTICO"
            fila["neto_diagnostico"] = resultado["neto_diagnostico"]
        else:
            fila["estado"] = "OPERANDOS_NO_RESUELTOS"
            fila["neto_diagnostico"] = None
        fila["certificado"] = False
    if resultados and len(resultados) != 4:
        raise ValueError("Se esperaban cuatro excepciones INC65")
    salida["inc65_excepcionales"] = resultados
    salida["certificado"] = False
    return salida
