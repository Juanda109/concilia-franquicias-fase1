import hashlib
import os
import tempfile
import uuid
from pathlib import Path

from fastapi import UploadFile


MAX_FILE_SIZE = 20 * 1024 * 1024


class ArchivoDemasiadoGrande(Exception):
    pass


def guardar_archivo(
    archivo: UploadFile,
    directorio: Path
) -> dict:
    directorio.mkdir(parents=True, exist_ok=True)

    checksum = hashlib.sha256()
    total_bytes = 0
    temporal = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=directorio,
            prefix=".upload_",
            delete=False
        ) as destino:
            temporal = Path(destino.name)

            while True:
                bloque = archivo.file.read(1024 * 1024)

                if not bloque:
                    break

                total_bytes += len(bloque)

                if total_bytes > MAX_FILE_SIZE:
                    raise ArchivoDemasiadoGrande(
                        "El archivo supera el limite permitido"
                    )

                checksum.update(bloque)
                destino.write(bloque)

        nombre_interno = f"{uuid.uuid4().hex}.bin"
        ruta_final = directorio / nombre_interno

        # El identificador aleatorio evita reutilizar el nombre del cliente.
        # Se publica el temporal con creacion exclusiva.
        with temporal.open("rb") as origen:
            with ruta_final.open("xb") as salida:
                while True:
                    bloque = origen.read(1024 * 1024)
                    if not bloque:
                        break
                    salida.write(bloque)

        temporal.unlink()

        return {
            "ruta": str(ruta_final.resolve()),
            "checksum_sha256": checksum.hexdigest(),
            "tamano_bytes": total_bytes,
            "nombre_original": Path(
                archivo.filename or "sin_nombre"
            ).name
        }

    except Exception:
        if temporal is not None:
            temporal.unlink(missing_ok=True)
        if "ruta_final" in locals():
            ruta_final.unlink(missing_ok=True)
        raise
