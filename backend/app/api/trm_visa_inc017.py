"""RECON_F2_017: consulta de TRM Visa, solo lectura."""

from fastapi import APIRouter, HTTPException
from psycopg import OperationalError, Error as PsycopgError

from app.repositories.database import connection
from app.repositories.trm_visa_inc017 import consultar_trm_vigente

router = APIRouter(
    prefix="/api/v1/jornadas",
    tags=["TRM Visa Fase 2"],
)


def esquema_trm_disponible():
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(
                "SELECT to_regclass('public.con_trm_jornada')"
            )
            return cur.fetchone()[0] is not None


@router.get(
    "/{id_jornada}/trm-visa",
    summary="Consultar TRM Visa de una jornada",
    description=(
        "Consulta de solo lectura. No confirma tasas, "
        "no convierte importes ni certifica conciliaciones."
    ),
)
def consultar_trm_visa(id_jornada: int):
    if id_jornada <= 0:
        raise HTTPException(
            status_code=422,
            detail="Jornada invalida",
        )

    try:
        if not esquema_trm_disponible():
            raise HTTPException(
                status_code=503,
                detail="Esquema TRM pendiente de instalacion",
            )

        resultado = consultar_trm_vigente(id_jornada)

        return {
            **resultado,
            "certificado": False,
            "conciliado_host": False,
        }

    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except (OperationalError, PsycopgError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible",
        ) from exc
