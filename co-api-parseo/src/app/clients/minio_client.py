import tempfile
from pathlib import Path
from minio import Minio
from app.core.config import settings

_client=Minio(settings.minio_endpoint,access_key=settings.minio_access_key,secret_key=settings.minio_secret_key,secure=settings.minio_secure)

def descargar(minio_key:str)->Path:
    suffix=Path(minio_key).suffix
    tmp=tempfile.NamedTemporaryFile(suffix=suffix,delete=False)
    tmp.close()
    _client.fget_object(settings.minio_bucket,minio_key,tmp.name)
    return Path(tmp.name)
