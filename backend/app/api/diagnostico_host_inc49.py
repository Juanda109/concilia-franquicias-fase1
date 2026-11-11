from fastapi import APIRouter
from app.services.fase2.diagnostico_host_inc49 import obtener_diagnostico_host
router = APIRouter(prefix="/api/v1")

@router.get("/jornadas/{id_jornada}/diagnostico-host-inc49")
def diagnostico_host_inc49(id_jornada: int):
    return obtener_diagnostico_host(id_jornada)
