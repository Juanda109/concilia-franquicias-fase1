"""RECON_F2_018 - Evidencia documental Visa por jornada."""

import hashlib
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row

from app.repositories.database import connection
from app.repositories.trm_visa_inc017 import consultar_trm_vigente
from app.services.fase2.trm_visa_inc017 import validar_trm, ErrorTRMVisa
from app.services.fase2.integracion_vss_inc018 import integrar_vss
from app.services.fase2.parser_vss_integral_inc018 import ErrorVSSIntegral

router = APIRouter(
    prefix="/api/v1/jornadas",
    tags=["Visa documental integral"],
)

MAX_BYTES = 20 * 1024 * 1024


def recuperar_vss(id_jornada):
    with connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("""
                SELECT j.fecha_contable,
                       i.id_archivo,
                       i.estado AS estado_insumo,
                       a.tipo_archivo,
                       a.fecha_contable AS fecha_archivo,
                       a.estado AS estado_archivo,
                       a.ruta_archivo,
                       a.checksum_sha256
                FROM public.con_jornada j
                JOIN public.con_insumo_esperado i
                  ON i.id_jornada = j.id_jornada
                 AND i.tipo_insumo = 'VSS'
                JOIN public.con_archivo_carga a
                  ON a.id_archivo = i.id_archivo
                WHERE j.id_jornada = %s
            """, (id_jornada,))
            filas = cur.fetchall()

    if len(filas) != 1:
        raise HTTPException(
            409, "VSS vigente ausente o ambiguo"
        )

    archivo = filas[0]

    if archivo["tipo_archivo"] != "VSS":
        raise HTTPException(409, "Tipo de archivo incorrecto")

    if archivo["fecha_archivo"] != archivo["fecha_contable"]:
        raise HTTPException(
            409, "Fecha del VSS diferente de la jornada"
        )

    if (
        archivo["estado_insumo"] != "PROCESADO"
        or archivo["estado_archivo"] != "PROCESADO"
    ):
        raise HTTPException(409, "VSS no procesado")

    raiz = os.environ.get("CONCILIA_ARCHIVOS_ROOT")

    if not raiz:
        raise HTTPException(
            503, "Directorio autorizado no configurado"
        )

    raiz = Path(raiz).resolve(strict=True)

    try:
        ruta = Path(archivo["ruta_archivo"]).resolve(strict=True)
    except (OSError, TypeError, ValueError) as exc:
        raise HTTPException(
            409, "Archivo VSS no disponible"
        ) from exc

    if not ruta.is_relative_to(raiz):
        raise HTTPException(403, "Ruta fuera de almacenamiento")

    if not ruta.is_file() or ruta.stat().st_size > MAX_BYTES:
        raise HTTPException(409, "Archivo no disponible o excede limite")

    checksum = str(archivo["checksum_sha256"] or "").strip().lower()

    if len(checksum) != 64 or any(
        c not in "0123456789abcdef" for c in checksum
    ):
        raise HTTPException(409, "Checksum VSS no disponible")

    contenido = ruta.read_bytes()

    if hashlib.sha256(contenido).hexdigest() != checksum:
        raise HTTPException(409, "Checksum VSS diferente")

    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = contenido.decode("cp1252")

    return archivo, texto


@router.get("/{id_jornada}/visa/documental-integral")
def consultar_visa_documental(id_jornada: int):
    if id_jornada <= 0:
        raise HTTPException(422, "Jornada invalida")


    archivo, texto = recuperar_vss(id_jornada)

    try:
        estado_trm = consultar_trm_vigente(id_jornada)
    except LookupError as exc:
        raise HTTPException(404, "Jornada inexistente") from exc
    except Exception as exc:
        from psycopg import Error as PsycopgError
        if isinstance(exc, PsycopgError):
            raise HTTPException(503, "TRM no disponible") from exc
        raise

    if estado_trm["estado"] == "SIN_TRM_CONFIRMADA":
        confirmacion = None
    elif estado_trm["estado"] == "TRM_CONFIRMADA":
        trm = estado_trm["trm"]
        if not isinstance(trm, dict):
            raise HTTPException(409, "Confirmacion TRM inconsistente")
        if (
            estado_trm["id_jornada"] != id_jornada
            or str(estado_trm["fecha_contable"]) != str(archivo["fecha_contable"])
        ):
            raise HTTPException(409, "Jornada TRM inconsistente")
        if (
            type(trm.get("version")) is not int
            or trm["version"] <= 0
            or str(trm.get("fecha_referencia"))
                != str(archivo["fecha_contable"])
        ):
            raise HTTPException(
                409, "Confirmacion TRM inconsistente"
            )

        try:
            validar_trm(trm.get("trm_aplicada"))
        except (ErrorTRMVisa, ValueError, TypeError) as exc:
            raise HTTPException(
                409, "Tasa TRM invalida"
            ) from exc

        confirmacion = {
            **trm,
            "estado": "TRM_CONFIRMADA",
            "confirmada": True,
            "id_jornada": id_jornada,
        }
    else:
        raise HTTPException(409, "Estado TRM desconocido")

    try:
        resultado = integrar_vss(
            id_jornada=id_jornada,
            id_archivo=archivo["id_archivo"],
            fecha_contable=archivo["fecha_contable"],
            contenido=texto,
            trm_confirmada=confirmacion,
        )
    except (ErrorVSSIntegral, ValueError) as exc:
        raise HTTPException(
            409, "Estructura documental VSS inconsistente"
        ) from exc

    return resultado
