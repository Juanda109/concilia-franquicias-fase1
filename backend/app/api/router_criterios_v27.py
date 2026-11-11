from fastapi import APIRouter
from app.services.fase2.criterios_v27 import generar_criterios
router=APIRouter(prefix='/api/v1/criterios-aceptacion',tags=['Pruebas no certificadas'])
@router.get('/v27')
def criterios_v27():
    return generar_criterios()
