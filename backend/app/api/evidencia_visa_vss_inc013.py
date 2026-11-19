from fastapi import APIRouter, HTTPException
from psycopg import OperationalError

from app.services.fase2.evidencia_visa_vss_inc013 import (
    consultar_evidencia_visa,
    EvidenciaVisaInconsistente,
)

router = APIRouter(prefix="/api/v1/jornadas", tags=["Visa Fase 2"])


@router.get(
    "/{id_jornada}/evidencia-visa-vss",
    summary="Evidencia documental Visa VSS",
    description=(
        "Consulta de solo lectura. No homologa cuentas, "
        "no concilia Host y no certifica importes."
    ),
)
def evidencia_visa_vss(id_jornada: int):
    if id_jornada <= 0:
        raise HTTPException(422, "Jornada invalida")

    try:
        return consultar_evidencia_visa(id_jornada)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except EvidenciaVisaInconsistente as exc:
        raise HTTPException(409, str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(503, "Base de datos no disponible") from exc
