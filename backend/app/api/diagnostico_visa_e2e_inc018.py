"""Diagnostico aislado Visa. Solo lectura, sin certificacion."""

import hashlib
import json
import os
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.ingestion.registry import obtener_parser
from app.services.fase2.integracion_vss_inc018 import integrar_vss

router = APIRouter(
    prefix="/api/v1/diagnostico/visa",
    tags=["Visa E2E - pruebas"],
)

CUENTAS = ("259095341", "299095888", "299095303")
FECHA = "2026-10-26"

HASH_VSS = (
    "f014611c474beac5e49ebef0ea90b4d3a3c90a04bce4fcb62e8a4568d91c9f64"
)


def importe(valor):
    numero = Decimal(str(valor))
    if not numero.is_finite():
        raise ValueError("Importe no finito")
    return numero


def verificar_archivo(ruta, checksum):
    if not ruta.is_file():
        raise ValueError("Archivo faltante")

    if ruta.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Archivo demasiado grande")

    datos = ruta.read_bytes()

    if hashlib.sha256(datos).hexdigest() != checksum.lower():
        raise ValueError("Checksum diferente")

    return datos


def obtener_escenario():
    raiz = os.environ.get("CONCILIA_VISA_E2E_ROOT")

    if not raiz:
        raise ValueError("Raiz de escenario no configurada")

    directorio = Path(raiz).resolve(strict=True)

    manifiesto_path = directorio / "manifiesto_host_visa.json"

    manifiesto = json.loads(
        manifiesto_path.read_text(encoding="utf-8-sig")
    )

    if (
        manifiesto.get("escenario") != "RECON_F2_VISA_20261026"
        or manifiesto.get("fecha_contable") != FECHA
        or set(manifiesto.get("archivos", {}))
           != {"HA22", "HA26", "HA32"}
    ):
        raise ValueError("Manifiesto inesperado")

    host = {}

    for tipo in ("HA22", "HA26", "HA32"):
        info = manifiesto["archivos"][tipo]

        nombre = info["nombre"]
        esperado = f"{tipo}_F261026_VISA_SINTETICO.txt"

        if nombre != esperado:
            raise ValueError("Nombre Host no autorizado")

        ruta = (directorio / nombre).resolve(strict=True)

        if ruta.parent != directorio:
            raise ValueError("Ruta Host no autorizada")

        verificar_archivo(ruta, info["sha256"])

        resultado = obtener_parser(tipo).parse(ruta)

        if resultado.errors or len(resultado.records) != 11:
            raise ValueError("Parser Host inconsistente")

        agrupado = defaultdict(
            lambda: {
                "movimientos": 0,
                "debe": Decimal("0"),
                "haber": Decimal("0"),
            }
        )

        for registro in resultado.records:
            cuenta = str(registro.get("NUCTA") or "").strip()

            if cuenta not in CUENTAS:
                continue

            datos = agrupado[cuenta]
            datos["movimientos"] += 1
            datos["debe"] += importe(registro["DEBE"])
            datos["haber"] += importe(registro["HABER"])

        if set(agrupado) != set(CUENTAS):
            raise ValueError("Cobertura Visa Host incompleta")

        host[tipo] = {
            cuenta: {
                "movimientos": datos["movimientos"],
                "debe_cop": str(datos["debe"]),
                "haber_cop": str(datos["haber"]),
                "neto_cop": str(
                    datos["debe"] - datos["haber"]
                ),
                "sintetico": True,
            }
            for cuenta, datos in agrupado.items()
        }

    ruta_vss = os.environ.get("CONCILIA_VISA_E2E_VSS")

    if not ruta_vss:
        raise ValueError("VSS de prueba no configurado")

    archivo_vss = Path(ruta_vss).resolve(strict=True)

    if archivo_vss.name.upper() != "VSS BBVA 26OCT26.TXT":
        raise ValueError("Nombre VSS no autorizado")

    contenido = verificar_archivo(archivo_vss, HASH_VSS)

    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = contenido.decode("cp1252")

    visa = integrar_vss(
        id_jornada=1,
        id_archivo=1,
        fecha_contable=FECHA,
        contenido=texto,
        trm_confirmada=None,
    )

    if visa["resumen_monetario"]["liquidacion_neta_usd"] != "529630.06":
        raise ValueError("Liquidacion VSS inesperada")

    return {
        "escenario": "RECON_F2_VISA_20261026",
        "fecha_contable": FECHA,
        "modo": "DIAGNOSTICO_AISLADO",
        "datos_host": "SINTETICOS",
        "datos_vss": "MUESTRA_DOCUMENTAL",
        "host": host,
        "visa": visa,
        "trm_confirmada": False,
        "certificado": False,
        "conciliado_host": False,
        "homologado_contablemente": False,
    }


@router.get("/2026-10-26")
def diagnostico_visa():
    if os.environ.get("CONCILIA_VISA_E2E_DIAGNOSTICO") != "1":
        raise HTTPException(404, "Diagnostico deshabilitado")

    if os.environ.get("DB_NAME") != "concilia_test":
        raise HTTPException(403, "Base no autorizada")

    try:
        return obtener_escenario()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise HTTPException(
            409, "Escenario Visa no valido o incompleto"
        ) from exc
