"""Endpoint diagnostico PMD INC59."""

from fastapi import APIRouter, HTTPException

from app.services.fase2.reporte_pmd_inc59 import consultar

router = APIRouter(
    prefix="/api/v1/jornadas",
    tags=["Reporte Maestro PMD Diagnostico"],
)


@router.get("/{id_jornada}/reporte-maestro-pmd-inc59")
def reporte_maestro_pmd_inc59(id_jornada: int):
    if id_jornada <= 0:
        raise HTTPException(
            status_code=422,
            detail="Jornada invalida",
        )

    try:
        return consultar(id_jornada)
    except ValueError as exc:
        if str(exc) == "Jornada inexistente":
            raise HTTPException(
                status_code=404,
                detail="Jornada no encontrada",
            ) from exc

        raise HTTPException(
            status_code=503,
            detail="Diagnostico PMD INC59 no disponible",
        ) from exc

    except (KeyError, OSError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Diagnostico PMD INC59 no disponible",
        ) from exc
