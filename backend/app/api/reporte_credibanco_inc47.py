"""Endpoint aditivo, no sustituye el diagnostico existente INC33."""
from fastapi import APIRouter, HTTPException
from app.services.fase2 import reporte_api_credibanco_inc47 as servicio

router = APIRouter(prefix='/api/v1/jornadas', tags=['Reporte Maestro Credibanco'])

@router.get('/{id_jornada}/reporte-maestro-credibanco')
def reporte_credibanco(id_jornada: int):
    if id_jornada <= 0:
        raise HTTPException(status_code=422, detail='Jornada invalida')
    try:
        return servicio.consultar(id_jornada)
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=503, detail='Diagnostico Credibanco no disponible') from exc
