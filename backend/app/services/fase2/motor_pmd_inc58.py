"""INC58: operaciones diagnosticas PMD Fase 2.

Sin homologacion contable, sin certificacion monetaria.
No modifica el contrato de Fase 1.
"""

from collections import Counter
from decimal import Decimal, InvalidOperation


MEDIDAS = frozenset({
    "DEBITO_CANTIDAD",
    "DEBITO_VALOR",
    "DEBITO_COMISION_INTERCAMBIO",
    "DEBITO_COMISION_ADMINISTRATIVA",
    "DEBITO_NETO",
    "CREDITO_CANTIDAD",
    "CREDITO_VALOR",
    "CREDITO_COMISION_INTERCAMBIO",
    "CREDITO_COMISION_ADMINISTRATIVA",
    "CREDITO_NETO",
    "TOTAL",
})


def decimal_exacto(valor):
    if valor is None or isinstance(valor, (bool, float)):
        raise ValueError("Importe ausente o no exacto")

    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Importe decimal invalido") from exc

    if not numero.is_finite():
        raise ValueError("Importe no finito")

    return numero


def normalizar_nivel(nivel):
    texto = str(nivel or "").strip()

    partes = texto.split(".")

    if not texto or not all(p.isdigit() for p in partes):
        raise ValueError("Nivel PMD invalido")

    return texto


def prefijo_codigo(codigo, longitud):
    if type(longitud) is not int or longitud <= 0:
        raise ValueError("Longitud invalida")

    return str(codigo)[:longitud]


def contar_codigo(codigos, codigo):
    return sum(1 for actual in codigos if actual == codigo)


def buscar_nivel(filas, nivel, medida):
    """Busqueda exacta diagnostica.

    No elige arbitrariamente entre niveles duplicados.
    """

    if medida not in MEDIDAS:
        raise ValueError("Medida PMD no autorizada")

    nivel = normalizar_nivel(nivel)

    coincidencias = [
        fila for fila in filas
        if not fila.get("ES_CONTROL")
        and normalizar_nivel(fila["NIVEL"]) == nivel
    ]

    if not coincidencias:
        return {
            "estado": "SIN_COINCIDENCIA",
            "valor": None,
            "lineas_origen": [],
        }

    if len(coincidencias) > 1:
        return {
            "estado": "NIVEL_DUPLICADO",
            "valor": None,
            "lineas_origen": [
                fila.get("numero_linea")
                for fila in coincidencias
            ],
        }

    fila = coincidencias[0]
    valor = fila.get(medida)

    return {
        "estado": "ENCONTRADO",
        "valor": str(decimal_exacto(valor))
                 if valor is not None else None,
        "lineas_origen": [fila.get("numero_linea")],
    }


def diagnosticar(filas, id_jornada):
    if type(id_jornada) is not int or id_jornada <= 0:
        raise ValueError("Jornada invalida")

    filas = list(filas)

    niveles = [
        normalizar_nivel(fila["NIVEL"])
        for fila in filas
        if not fila.get("ES_CONTROL")
    ]

    conteos = Counter(niveles)

    duplicados = {
        nivel: cantidad
        for nivel, cantidad in conteos.items()
        if cantidad > 1
    }

    return {
        "id_jornada": id_jornada,
        "fuente": "PMD",
        "incremento": 58,
        "cantidad_registros": len(filas),
        "cantidad_controles": sum(
            1 for fila in filas if fila.get("ES_CONTROL")
        ),
        "niveles_duplicados": duplicados,
        "certificado": False,
        "valor_franquicia_certificado": None,
        "total_host_homologado": None,
        "diferencia_certificada": None,
        "estado": "DIAGNOSTICO_NO_HOMOLOGADO",
    }



def buscar_indice_plantilla(filas, nivel, indice):
    """Busqueda diagnostica equivalente a VLOOKUP exacto.

    No convierte automaticamente SIN_COINCIDENCIA en cero.
    No certifica importes contables.
    """
    from app.services.fase2.catalogo_medidas_pmd_inc58 import (
        medida_plantilla,
        columna_plantilla,
    )

    medida = medida_plantilla(indice)
    columna = columna_plantilla(indice)

    resultado = buscar_nivel(filas, nivel, medida)

    return {
        "nivel": normalizar_nivel(nivel),
        "indice_excel": indice,
        "columna_plantilla": columna,
        "medida": medida,
        "estado": resultado["estado"],
        "valor": resultado["valor"],
        "lineas_origen": resultado["lineas_origen"],
        "certificado": False,
    }


def calcular_neto_estructura(filas, nivel):
    """ESTRUCTURA N/O/P: calculo diagnostico no certificado."""
    debito = buscar_indice_plantilla(filas, nivel, 3)
    credito = buscar_indice_plantilla(filas, nivel, 8)

    estados = (debito["estado"], credito["estado"])

    resultado = {
        "nivel": normalizar_nivel(nivel),
        "regla": "PMD_F2_ESTRUCTURA_NETO",
        "debito": debito,
        "credito": credito,
        "signo_credito": -1,
        "neto_diagnostico": None,
        "certificado": False,
        "valor_franquicia_certificado": None,
        "diferencia_certificada": None,
    }

    if estados != ("ENCONTRADO", "ENCONTRADO"):
        resultado["estado"] = "OPERANDOS_NO_RESUELTOS"
        return resultado

    if debito["valor"] is None or credito["valor"] is None:
        resultado["estado"] = "VALOR_AUSENTE"
        return resultado

    valor_debito = decimal_exacto(debito["valor"])
    valor_credito = decimal_exacto(credito["valor"])

    resultado["neto_diagnostico"] = str(
        valor_debito - valor_credito
    )
    resultado["estado"] = "CALCULO_DIAGNOSTICO"

    return resultado


def diagnosticar_validador(filas, nivel):
    """Recupera medidas PMD utilizadas por VALIDADOR.

    No ejecuta F4+J4 sin identificar ambos operandos.
    No certifica conciliacion.
    """
    medidas = {
        "debito_neto": buscar_indice_plantilla(filas, nivel, 6),
        "credito_neto": buscar_indice_plantilla(filas, nivel, 11),
        "total_pmd": buscar_indice_plantilla(filas, nivel, 12),
    }

    estados = {
        nombre: dato["estado"]
        for nombre, dato in medidas.items()
    }

    completo = all(
        estado == "ENCONTRADO"
        for estado in estados.values()
    )

    return {
        "nivel": normalizar_nivel(nivel),
        "reglas": [
            "PMD-F2-005",
            "PMD-F2-006",
            "PMD-F2-007",
        ],
        "medidas": medidas,
        "estados": estados,
        "estado": (
            "MEDIDAS_RECUPERADAS"
            if completo else "MEDIDAS_INCOMPLETAS"
        ),
        "control_f4_j4": None,
        "certificado": False,
        "diferencia_certificada": None,
    }


def calcular_control_validador(
    filas, nivel, neto_estructura, referencia_estructura
):
    """VALIDADOR: F + J. Diagnostico no certificado.

    F: neto de ESTRUCTURA.
    J: total PMD obtenido por busqueda exacta.
    """
    if not referencia_estructura:
        raise ValueError("Referencia de estructura requerida")

    total_pmd = buscar_indice_plantilla(filas, nivel, 12)

    resultado = {
        "nivel": normalizar_nivel(nivel),
        "regla": "PMD-F2-008",
        "referencia_estructura": referencia_estructura,
        "neto_estructura": None,
        "total_pmd": total_pmd,
        "control_diagnostico": None,
        "estado": "OPERANDOS_NO_RESUELTOS",
        "certificado": False,
        "diferencia_certificada": None,
    }

    if neto_estructura is None:
        return resultado

    resultado["neto_estructura"] = str(
        decimal_exacto(neto_estructura)
    )

    if total_pmd["estado"] != "ENCONTRADO":
        return resultado

    if total_pmd["valor"] is None:
        resultado["estado"] = "VALOR_AUSENTE"
        return resultado

    valor_pmd = decimal_exacto(total_pmd["valor"])
    valor_estructura = decimal_exacto(neto_estructura)

    resultado["control_diagnostico"] = str(
        valor_estructura + valor_pmd
    )
    resultado["estado"] = "CONTROL_DIAGNOSTICO"

    return resultado


def diagnosticar_estructura_2(filas, codigo_operacion):
    """ESTRUCTURA 2: F/G/M/N/O/P/Q.

    Diagnostico no certificado.
    Sin conversion automatica IFERROR a cero.
    """
    codigo = normalizar_nivel(codigo_operacion)

    indices = {
        "debito_valor": 3,
        "credito_valor": 8,
        "debito_cantidad": 2,
        "credito_cantidad": 7,
    }

    medidas = {
        nombre: buscar_indice_plantilla(filas, codigo, indice)
        for nombre, indice in indices.items()
    }

    resultado = {
        "codigo_operacion": codigo,
        "prefijo_3": prefijo_codigo(codigo, 3),
        "prefijo_5": prefijo_codigo(codigo, 5),
        "medidas": medidas,
        "credito_firmado": None,
        "neto_diagnostico": None,
        "fecha_cuadre": None,
        "estado": "OPERANDOS_NO_RESUELTOS",
        "certificado": False,
        "diferencia_certificada": None,
    }

    if any(
        dato["estado"] != "ENCONTRADO"
        for dato in medidas.values()
    ):
        return resultado

    if any(dato["valor"] is None for dato in medidas.values()):
        resultado["estado"] = "VALOR_AUSENTE"
        return resultado

    debito = decimal_exacto(medidas["debito_valor"]["valor"])
    credito = decimal_exacto(medidas["credito_valor"]["valor"])

    resultado["credito_firmado"] = str(-credito)
    resultado["neto_diagnostico"] = str(debito - credito)
    resultado["estado"] = "CALCULO_DIAGNOSTICO"

    return resultado


def buscar_indice_iferror(filas, nivel, indice):
    """Adaptador diagnostico IFERROR(VLOOKUP(...),0).

    Solo SIN_COINCIDENCIA se convierte en cero.
    Duplicados y valores nulos no se homologan.
    """
    resultado = buscar_indice_plantilla(filas, nivel, indice)

    salida = dict(resultado)
    salida["estado_original"] = resultado["estado"]
    salida["cero_por_ausencia"] = False
    salida["certificado"] = False

    if resultado["estado"] == "SIN_COINCIDENCIA":
        salida["valor"] = "0"
        salida["estado"] = "CERO_POR_AUSENCIA"
        salida["cero_por_ausencia"] = True

    return salida
