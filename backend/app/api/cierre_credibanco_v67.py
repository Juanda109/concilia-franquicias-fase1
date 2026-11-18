"""Endpoint aditivo de solo lectura para Credibanco F2, sin Excel."""
from fastapi import APIRouter, HTTPException
from app.services.fase2.cierre_credibanco_pg_v67 import ejecutar

router = APIRouter(prefix="/api/v1/jornadas", tags=["Credibanco F2 - control seguro"])


@router.get("/{id_jornada}/cierre-credibanco-diagnostico")
def cierre_credibanco_diagnostico(id_jornada: int):
    if id_jornada <= 0:
        raise HTTPException(status_code=422, detail="Jornada invalida")
    try:
        resultado = ejecutar(id_jornada)
    except (ValueError, RuntimeError) as exc:
        # Error de integridad/entrada: no devolver false positivo de cuadre.
        raise HTTPException(status_code=409, detail="Datos de conciliacion inconsistentes") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Diagnostico Credibanco no disponible") from exc
    if resultado is None:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    return resultado
