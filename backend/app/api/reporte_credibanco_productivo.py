from fastapi import APIRouter, HTTPException

from app.services.fase2.reporte_credibanco_productivo import consultar

router = APIRouter(prefix="/api/v1/jornadas", tags=["Conciliacion Credibanco Productiva"])


@router.get("/{id_jornada}/conciliacion-credibanco")
def conciliacion_credibanco(id_jornada: int):
    if id_jornada <= 0:
        raise HTTPException(status_code=422, detail="Jornada invalida")
    try:
        return consultar(id_jornada)
    except (ValueError, KeyError, OSError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
