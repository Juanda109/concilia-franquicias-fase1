"""RECON_F2_017 Lote 8: propuesta de TRM Visa.

Solo lectura. No confirma tasas, no escribe en PostgreSQL
y no certifica conciliaciones.
"""

from datetime import date

from fastapi import APIRouter, HTTPException
from psycopg import Error as PsycopgError

from app.repositories.database import connection
from app.services.fase2.cliente_http_trm_inc017 import (
    consultar_trm_http,
    ErrorConsultaTRM,
)

router = APIRouter(
    prefix="/api/v1/jornadas",
    tags=["TRM Visa Fase 2"],
)


def consultar_fecha_contable(id_jornada: int) -> date:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")

            cur.execute("""
                SELECT fecha_contable
                FROM public.con_jornada
                WHERE id_jornada = %s
            """, (id_jornada,))

            fila = cur.fetchone()

    if fila is None:
        raise LookupError("Jornada inexistente")

    if type(fila[0]) is not date:
        raise ValueError("Fecha contable invalida")

    return fila[0]


@router.get(
    "/{id_jornada}/trm-visa/propuesta",
    summary="Consultar propuesta oficial de TRM Visa",
    description=(
        "Consulta la TRM correspondiente a la fecha contable "
        "de la jornada. No confirma tasas, no realiza "
        "conversiones ni certifica conciliaciones."
    ),
)
def propuesta_trm_visa(id_jornada: int):
    if id_jornada <= 0:
        raise HTTPException(
            status_code=422,
            detail="Jornada invalida",
        )

    try:
        fecha = consultar_fecha_contable(id_jornada)

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail="Jornada inexistente",
        ) from exc

    except PsycopgError as exc:
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail="Fecha contable inconsistente",
        ) from exc

    try:
        propuesta = consultar_trm_http(fecha)

    except ErrorConsultaTRM as exc:
        raise HTTPException(
            status_code=503,
            detail="Fuente oficial TRM no disponible",
        ) from exc

    if (
        propuesta.get("fecha_referencia") != fecha.isoformat()
        or propuesta.get("confirmada") is not False
        or propuesta.get("certificado") is not False
        or propuesta.get("conciliado_host") is not False
    ):
        raise HTTPException(
            status_code=409,
            detail="Respuesta TRM inconsistente",
        )

    return {
        "id_jornada": id_jornada,
        "fecha_contable": fecha.isoformat(),
        **propuesta,
        "confirmada": False,
        "certificado": False,
        "conciliado_host": False,
    }
