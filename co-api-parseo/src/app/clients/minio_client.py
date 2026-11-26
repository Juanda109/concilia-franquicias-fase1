import os
import shutil
import tempfile
from pathlib import Path
from app.core.config import settings

_LOCAL = settings.storage_backend == "local"

if not _LOCAL:
    from minio import Minio
    _client=Minio(settings.minio_endpoint,access_key=settings.minio_access_key,secret_key=settings.minio_secret_key,secure=settings.minio_secure)

def _sufijo_seguro(minio_key:str)->str:
    # El sufijo del temporal nunca sale del nombre del objeto: se devuelve
    # una constante de esta lista (extensiones de nombres_archivo.py del backend).
    ext=os.path.splitext(minio_key)[1].lower()
    for permitida in (".txt",".csv",".xls",".xlsx",".pdf"):
        if ext==permitida:
            return permitida
    return ""

def _ruta_local(minio_key:str)->str:
    base=os.path.realpath(settings.storage_path)
    ruta=os.path.realpath(os.path.join(base,minio_key))
    if not ruta.startswith(base+os.sep):
        raise ValueError(f"Clave de almacenamiento fuera del directorio permitido: {minio_key!r}")
    return ruta

def descargar(minio_key:str)->Path:
    tmp=tempfile.NamedTemporaryFile(suffix=_sufijo_seguro(minio_key),delete=False)
    tmp.close()
    if _LOCAL:
        shutil.copy(_ruta_local(minio_key),tmp.name)
        return Path(tmp.name)
    _client.fget_object(settings.minio_bucket,minio_key,tmp.name)
    return Path(tmp.name)
