"""Endpoint aditivo INC51, sin alterar INC50."""
from fastapi import APIRouter, HTTPException
from app.services.fase2.reporte_credibanco_inc51 import consultar
router=APIRouter(prefix='/api/v1/jornadas', tags=['Reporte Maestro Credibanco Diagnostico'])
@router.get('/{id_jornada}/reporte-maestro-inc51')
def reporte_maestro_inc51(id_jornada:int, fuente_host: str | None = None):
    if id_jornada <= 0: raise HTTPException(status_code=422, detail='Jornada invalida')
    if fuente_host is not None and fuente_host not in ('HA22','HA26','HA32'):
        raise HTTPException(status_code=422, detail='fuente_host invalida')
    try: return consultar(id_jornada, fuente_host=fuente_host)
    except (ValueError,KeyError,OSError) as exc:
        raise HTTPException(status_code=503,detail='Diagnostico INC51 no disponible') from exc
