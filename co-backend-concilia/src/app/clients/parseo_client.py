import httpx
from fastapi import HTTPException
from app.core.config import settings

def parsear(id_archivo:int,tipo_insumo:str,minio_key:str,correlation_id:str)->dict:
    try:
        r=httpx.post(f"{settings.parseo_api_url}/parse",json={
            "idArchivo":id_archivo,"tipoInsumo":tipo_insumo,
            "minioKey":minio_key,"correlationId":correlation_id,
        # /parse inserta registro a registro y un archivo grande (ej. CAET,
        # ~370k filas) tarda varios minutos: un timeout corto aquí no cancela
        # el proceso en parseo (sigue corriendo del lado del servidor), solo
        # hace que el backend marque "Error" prematuramente mientras parseo
        # termina bien más tarde y sobreescribe el estado. connect=10s para
        # fallar rápido si parseo de plano no está alcanzable.
        },timeout=httpx.Timeout(1800.0,connect=10.0))
    except httpx.RequestError as exc:
        raise HTTPException(503,f"API_PARSEO_NO_DISPONIBLE: {exc}")
    if r.status_code>=400:
        raise HTTPException(r.status_code,r.json().get("detail",r.text))
    return r.json()
