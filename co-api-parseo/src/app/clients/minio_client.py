import os
import tempfile
from pathlib import Path
from minio import Minio
from app.core.config import settings

_client=Minio(settings.minio_endpoint,access_key=settings.minio_access_key,secret_key=settings.minio_secret_key,secure=settings.minio_secure)


def _sufijo_seguro(minio_key:str)->str:
    # El sufijo del temporal nunca sale del nombre del objeto: se devuelve
    # una constante de esta lista (extensiones de nombres_archivo.py del backend).
    ext=os.path.splitext(minio_key)[1].lower()
    for permitida in (".txt",".csv",".xls",".xlsx",".pdf"):
        if ext==permitida:
            return permitida
    return ""


def descargar(minio_key:str)->Path:
    tmp=tempfile.NamedTemporaryFile(suffix=_sufijo_seguro(minio_key),delete=False)
    tmp.close()
    _client.fget_object(settings.minio_bucket,minio_key,tmp.name)
    return Path(tmp.name)
