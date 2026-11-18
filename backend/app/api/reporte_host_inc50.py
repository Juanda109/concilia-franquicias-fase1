"""Endpoint aditivo INC50, diagnostico no certificado."""
from fastapi import APIRouter, HTTPException
from app.services.fase2 import reporte_host_inc50 as servicio
router=APIRouter(prefix='/api/v1/jornadas', tags=['Reporte Maestro Host Diagnostico'])
@router.get('/{id_jornada}/reporte-maestro-host-inc50')
def reporte_host_inc50(id_jornada: int):
    if id_jornada <= 0: raise HTTPException(status_code=422, detail='Jornada invalida')
    try: return servicio.consultar(id_jornada)
    except (ValueError, KeyError, OSError) as exc:
        raise HTTPException(status_code=503, detail='Diagnostico Host no disponible') from exc
