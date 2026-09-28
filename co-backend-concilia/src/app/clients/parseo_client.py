import httpx
from fastapi import HTTPException
from app.core.config import settings

def parsear(id_archivo:int,tipo_insumo:str,minio_key:str,correlation_id:str)->dict:
    try:
        r=httpx.post(f"{settings.parseo_api_url}/parse",json={
            "idArchivo":id_archivo,"tipoInsumo":tipo_insumo,
            "minioKey":minio_key,"correlationId":correlation_id,
        },timeout=60.0)
    except httpx.RequestError as exc:
        raise HTTPException(503,f"API_PARSEO_NO_DISPONIBLE: {exc}")
    if r.status_code>=400:
        raise HTTPException(r.status_code,r.json().get("detail",r.text))
    return r.json()
