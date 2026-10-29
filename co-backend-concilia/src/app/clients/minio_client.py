import io
from minio import Minio
from app.core.config import settings

_client=Minio(settings.minio_endpoint,access_key=settings.minio_access_key,secret_key=settings.minio_secret_key,secure=settings.minio_secure)

def _asegurar_bucket():
    if not _client.bucket_exists(settings.minio_bucket):
        _client.make_bucket(settings.minio_bucket)

def subir(minio_key:str,contenido:bytes):
    _asegurar_bucket()
    _client.put_object(settings.minio_bucket,minio_key,io.BytesIO(contenido),length=len(contenido))

def eliminar(minio_key:str):
    if _LOCAL:
        Path(settings.storage_path).joinpath(minio_key).unlink(missing_ok=True)
        return
    # remove_object no falla si la llave no existe (ej. un archivo rechazado
    # antes de llegar a subirse nunca tuvo objeto real en el bucket).
    _client.remove_object(settings.minio_bucket,minio_key)
