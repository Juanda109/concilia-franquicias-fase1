import io
from pathlib import Path
from app.core.config import settings

_LOCAL = settings.storage_backend == "local"

if not _LOCAL:
    from minio import Minio
    _client=Minio(settings.minio_endpoint,access_key=settings.minio_access_key,secret_key=settings.minio_secret_key,secure=settings.minio_secure)

def _asegurar_bucket():
    if not _client.bucket_exists(settings.minio_bucket):
        _client.make_bucket(settings.minio_bucket)

def subir(minio_key:str,contenido:bytes):
    if _LOCAL:
        destino=Path(settings.storage_path)/minio_key
        destino.parent.mkdir(parents=True,exist_ok=True)
        destino.write_bytes(contenido)
        return
    _asegurar_bucket()
    _client.put_object(settings.minio_bucket,minio_key,io.BytesIO(contenido),length=len(contenido))
