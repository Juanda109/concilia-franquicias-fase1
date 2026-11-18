from fastapi import APIRouter, HTTPException
from app.services.fase2.servicio_v24 import diagnosticar

router=APIRouter(prefix='/api/v1/auditoria-monetaria',tags=['Auditoria monetaria no certificada'])

@router.get('/jornadas/{id_jornada}')
def auditoria_monetaria_v24(id_jornada:int):
    if id_jornada<=0:
        raise HTTPException(status_code=422,detail='Jornada invalida')
    try:
        resultado=diagnosticar(id_jornada)
    except Exception as exc:
        from psycopg import OperationalError
        if isinstance(exc,(OperationalError,KeyError)):
            raise HTTPException(status_code=503,detail='Base de datos no disponible') from exc
        raise
    if resultado is None:
        raise HTTPException(status_code=404,detail='Jornada no encontrada')
    return resultado
