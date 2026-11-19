"""RECON_F2_018: lectura documental integral VSS.

No convierte monedas, no homologa cuentas y no escribe en BD.
"""
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

CABECERA = re.compile(r"REPORT ID:\s*(VSS-\d+)")
PAGINA = re.compile(r"PAGE:\s*(\d+)")
MONEDA = re.compile(r"SETTLEMENT CURRENCY:\s*([A-Z]{3})")
CLEARING = re.compile(r"CLEARING CURRENCY:\s*([A-Z]{3})")
ENTIDAD = re.compile(r"FUNDS XFER ENTITY:\s*(\d+)")
IMPORTE = re.compile(r"(\d[\d,]*\.\d{2})(CR|DB)?")

REPORTES = {"VSS-110", "VSS-115", "VSS-120"}


class ErrorVSSIntegral(ValueError):
    pass


def decimal_vss(texto):
    try:
        valor = Decimal(texto.replace(",", ""))
    except (InvalidOperation, AttributeError) as exc:
        raise ErrorVSSIntegral("Importe VSS invalido") from exc
    if not valor.is_finite():
        raise ErrorVSSIntegral("Importe VSS no finito")
    return valor


def importar_lineas(texto):
    if not isinstance(texto, str):
        raise ErrorVSSIntegral("Contenido invalido")

    registros = []
    contexto = None

    for numero, linea in enumerate(texto.splitlines(), 1):
        cabecera = CABECERA.search(linea)

        if cabecera:
            reporte = cabecera.group(1)
            pagina = PAGINA.search(linea)
            contexto = {
                "reporte": reporte,
                "pagina": int(pagina.group(1)) if pagina else None,
                "moneda_liquidacion": None,
                "moneda_clearing": None,
                "entidad": None,
            }

        if contexto is None:
            continue

        liquidacion = MONEDA.search(linea)
        clearing = CLEARING.search(linea)
        entidad = ENTIDAD.search(linea)

        if liquidacion:
            contexto["moneda_liquidacion"] = liquidacion.group(1)
        if clearing:
            contexto["moneda_clearing"] = clearing.group(1)
        if entidad:
            contexto["entidad"] = entidad.group(1)

        registros.append({
            **contexto,
            "linea_origen": numero,
            "texto_original": linea,
        })

    return registros


def ultimo_importe(linea):
    valores = list(IMPORTE.finditer(linea))
    if not valores:
        raise ErrorVSSIntegral("Linea sin importe")
    ultimo = valores[-1]
    valor = decimal_vss(ultimo.group(1))
    signo = ultimo.group(2) or None
    return {
        "importe": str(valor),
        "signo": signo,
        "valor_firmado": str(-valor if signo == "DB" else valor),
    }


def extraer_resumen(texto):
    registros = importar_lineas(texto)
    reportes = {}
    evidencias = []

    for fila in registros:
        reporte = fila["reporte"]
        if reporte not in REPORTES:
            continue

        grupo = reportes.setdefault(reporte, {
            "paginas": set(),
            "monedas_liquidacion": set(),
            "monedas_clearing": set(),
            "entidades": set(),
        })

        if fila["pagina"] is not None:
            grupo["paginas"].add(fila["pagina"])
        if fila["moneda_liquidacion"]:
            grupo["monedas_liquidacion"].add(
                fila["moneda_liquidacion"]
            )
        if fila["moneda_clearing"]:
            grupo["monedas_clearing"].add(
                fila["moneda_clearing"]
            )
        if fila["entidad"]:
            grupo["entidades"].add(fila["entidad"])

        linea = fila["texto_original"].strip()
        concepto = None

        if reporte == "VSS-110" and linea.startswith(
            "NET SETTLEMENT AMOUNT"
        ):
            concepto = "LIQUIDACION_NETA"

        elif reporte == "VSS-115" and linea.startswith(
            "FINAL SETTLEMENT NET AMOUNT"
        ):
            concepto = "LIQUIDACION_NETA_CONTROL"

        elif reporte == "VSS-120":
            if linea.startswith("TOTAL ORIGINAL SALE"):
                concepto = "CLEARING_VENTAS"
            elif linea.startswith("TOTAL ACQUIRER INTERCHANGE"):
                concepto = "INTERCHANGE_DETALLE"

        if concepto:
            importe = ultimo_importe(linea)
            evidencias.append({
                "reporte": reporte,
                "pagina": fila["pagina"],
                "linea_origen": fila["linea_origen"],
                "concepto": concepto,
                "moneda_liquidacion": fila["moneda_liquidacion"],
                "moneda_clearing": fila["moneda_clearing"],
                "entidad": fila["entidad"],
                "texto_original": fila["texto_original"],
                **importe,
            })

    salida_reportes = {
        nombre: {
            "paginas": sorted(grupo["paginas"]),
            "monedas_liquidacion": sorted(
                grupo["monedas_liquidacion"]
            ),
            "monedas_clearing": sorted(
                grupo["monedas_clearing"]
            ),
            "entidades": sorted(grupo["entidades"]),
        }
        for nombre, grupo in reportes.items()
    }

    netos = {
        e["reporte"]: Decimal(e["valor_firmado"])
        for e in evidencias
        if e["concepto"] in (
            "LIQUIDACION_NETA",
            "LIQUIDACION_NETA_CONTROL",
        )
    }

    paridad = (
        netos["VSS-110"] == netos["VSS-115"]
        if "VSS-110" in netos and "VSS-115" in netos
        else None
    )

    return {
        "reportes": salida_reportes,
        "evidencias": evidencias,
        "paridad_110_115": paridad,
        "liquidacion_unica_usd": (
            str(netos["VSS-110"])
            if paridad is True else None
        ),
        "certificado": False,
        "conciliado_host": False,
    }


def analizar_archivo(ruta):
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(ruta)

    contenido = ruta.read_bytes()

    # Los reportes VSS de texto pueden contener saltos de pagina.
    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = contenido.decode("cp1252")

    return extraer_resumen(texto)
