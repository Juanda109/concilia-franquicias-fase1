from fastapi import APIRouter,HTTPException
from app.services.fase2.servicio_v26 import diagnosticar_v26
router=APIRouter(prefix='/api/v1/motor-v26',tags=['Motor monetario V26 no certificado'])
@router.get('/jornadas/{id_jornada}')
def motor_v26(id_jornada:int):
    if id_jornada<=0:raise HTTPException(status_code=422,detail='Jornada invalida')
    try:
        resultado=diagnosticar_v26(id_jornada)
    except Exception as exc:
        from psycopg import OperationalError
        if isinstance(exc,(OperationalError,KeyError)):
            raise HTTPException(status_code=503,detail='Consulta no disponible') from exc
        raise
    if resultado is None:raise HTTPException(status_code=404,detail='Jornada no encontrada')
    return resultado
