"""API de consolidacion tecnica y trazabilidad MVP1."""

from fastapi import APIRouter, HTTPException, Depends
from psycopg import OperationalError, errors
from psycopg.rows import dict_row

from app.repositories.database import connection
from app.services.consolidacion_jornada import (
    consolidar_jornada,
    ConsolidacionJornadaError,
    JornadaNoEncontrada,
    JornadaIncompleta,
)

router = APIRouter(
    prefix="/api/v1/jornadas",
    tags=["Consolidacion tecnica"],
)





def autorizar_consolidacion():
    """Cerrado por defecto hasta integrar identidad corporativa."""
    raise HTTPException(
        status_code=403,
        detail={
            "codigo": "CONSOLIDACION_NO_AUTORIZADA",
            "mensaje": "Autorizacion corporativa no configurada",
        },
    )


@router.post("/{id_jornada}/consolidar")
def consolidar(
    id_jornada: int,
    _autorizacion=Depends(autorizar_consolidacion),
):
    if id_jornada <= 0:
        raise HTTPException(
            status_code=422,
            detail="Identificador de jornada invalido",
        )

    try:
        return consolidar_jornada(id_jornada)

    except JornadaNoEncontrada as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except (JornadaIncompleta, ConsolidacionJornadaError) as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except errors.LockNotAvailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Jornada temporalmente bloqueada",
            headers={"Retry-After": "5"},
        ) from exc

    except (OperationalError, KeyError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible",
        ) from exc


@router.get("/{id_jornada}/trazabilidad")
def consultar_trazabilidad(id_jornada: int):
    if id_jornada <= 0:
        raise HTTPException(
            status_code=422,
            detail="Identificador de jornada invalido",
        )

    try:
        with connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SET TRANSACTION READ ONLY")

                cur.execute("""
                    SELECT id_jornada
                    FROM public.con_jornada
                    WHERE id_jornada = %s
                """, (id_jornada,))

                if cur.fetchone() is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Jornada no encontrada",
                    )

                cur.execute("""
                    SELECT
                        correlation_id,
                        id_jornada,
                        id_archivo,
                        tipo_evento,
                        componente,
                        detalle,
                        fec_evento
                    FROM public.con_trazabilidad
                    WHERE id_jornada = %s
                    ORDER BY fec_evento, correlation_id
                """, (id_jornada,))

                eventos = cur.fetchall()

                return {
                    "id_jornada": id_jornada,
                    "total_eventos": len(eventos),
                    "eventos": eventos,
                }

    except (OperationalError, KeyError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible",
        ) from exc
