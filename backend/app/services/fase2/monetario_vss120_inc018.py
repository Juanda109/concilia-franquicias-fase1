"""RECON_F2_018: extraccion monetaria VSS-120.

Solo lectura documental. No homologa cuentas ni certifica.
"""

import re
from decimal import Decimal

from app.services.fase2.parser_vss_integral_inc018 import (
    importar_lineas,
    decimal_vss,
    ErrorVSSIntegral,
)

IMPORTE = re.compile(r"(\d[\d,]*\.\d{2})(CR|DB)?")

# Posiciones verificadas contra la muestra de produccion.
# Se validan las cabeceras antes de usar estas columnas.
COLUMNAS = (
    ("clearing", 67, 98),
    ("interchange_credito", 98, 120),
    ("interchange_debito", 120, None),
)


def leer_importe(segmento):
    valores = list(IMPORTE.finditer(segmento))

    if not valores:
        return None

    if len(valores) != 1:
        raise ErrorVSSIntegral(
            "Multiples importes en una columna"
        )

    valor = valores[0]
    numero = decimal_vss(valor.group(1))
    signo = valor.group(2)

    return {
        "importe": str(numero),
        "signo": signo,
        "valor_firmado": str(
            -numero if signo == "DB" else numero
        ),
    }


def extraer_vss120(texto):
    lineas = importar_lineas(texto)
    evidencias = []

    cabeceras = set()

    for fila in lineas:
        if fila["reporte"] != "VSS-120":
            continue

        pagina = fila["pagina"]
        linea = fila["texto_original"]
        etiqueta = linea.strip()

        if (
            "CLEARING" in linea
            and "INTERCHANGE" in linea
            and "RATE" in linea
        ):
            cabeceras.add(pagina)

        if pagina not in cabeceras:
            continue

        if etiqueta.startswith("TOTAL ORIGINAL SALE"):
            concepto = "TOTAL_ORIGINAL_SALE"
        elif etiqueta.startswith("TOTAL ACQUIRER INTERCHANGE"):
            concepto = "TOTAL_ACQUIRER_INTERCHANGE"
        elif etiqueta.startswith("DISPUTE RESP FIN"):
            concepto = "DISPUTE_RESP_FIN"
        elif etiqueta.startswith("DISPUTE FIN"):
            concepto = "DISPUTE_FIN"
        elif etiqueta.startswith("ORIGINAL SALE"):
            concepto = "ORIGINAL_SALE"
        elif re.match(r"^A\d{4}\s", etiqueta):
            concepto = "ORIGINAL_SALE_CONTINUACION"
        else:
            continue

        importes = {}

        for nombre, inicio, fin in COLUMNAS:
            importes[nombre] = leer_importe(
                linea[inicio:fin]
            )

        evidencias.append({
            "reporte": "VSS-120",
            "pagina": pagina,
            "linea_origen": fila["linea_origen"],
            "concepto": concepto,
            "moneda_clearing": fila["moneda_clearing"],
            "moneda_liquidacion": fila["moneda_liquidacion"],
            "texto_original": linea,
            **importes,
        })

    return evidencias


def validar_muestra_vss120(evidencias):
    def unico(concepto, pagina):
        encontrados = [
            e for e in evidencias
            if e["concepto"] == concepto
            and e["pagina"] == pagina
        ]

        if len(encontrados) != 1:
            raise ErrorVSSIntegral(
                f"Evidencia ambigua: {concepto}, pagina {pagina}"
            )

        return encontrados[0]

    ventas = unico("TOTAL_ORIGINAL_SALE", 1)
    disputas = unico("TOTAL_ACQUIRER_INTERCHANGE", 2)

    if ventas["moneda_clearing"] != "COP":
        raise ErrorVSSIntegral("Moneda clearing COP invalida")

    if disputas["moneda_clearing"] != "USD":
        raise ErrorVSSIntegral("Moneda clearing USD invalida")

    cop = Decimal(
        ventas["clearing"]["valor_firmado"]
    )

    credito = Decimal(
        ventas["interchange_credito"]["importe"]
    ) + Decimal(
        disputas["interchange_credito"]["importe"]
    )

    debito = Decimal(
        disputas["interchange_debito"]["importe"]
    )

    return {
        "clearing_ventas_cop": str(cop),
        "interchange_credito_usd": str(credito),
        "interchange_debito_usd": str(debito),
        "interchange_neto_usd": str(credito - debito),
        "certificado": False,
        "conciliado_host": False,
    }
