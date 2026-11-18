import hashlib
from io import BytesIO

import pytest
from fastapi import UploadFile

from app.services.almacenamiento import (
    ArchivoDemasiadoGrande,
    guardar_archivo,
)


def test_guardar_archivo(tmp_path):
    contenido = b"CONCILIA-ARCHIVO-PRUEBA"

    archivo = UploadFile(
        file=BytesIO(contenido),
        filename="prueba.txt"
    )

    resultado = guardar_archivo(archivo, tmp_path)

    from pathlib import Path
    ruta = Path(resultado["ruta"])

    assert ruta.exists()
    assert ruta.read_bytes() == contenido
    assert resultado["tamano_bytes"] == len(contenido)
    assert resultado["checksum_sha256"] == hashlib.sha256(
        contenido
    ).hexdigest()


def test_archivo_demasiado_grande(tmp_path):
    contenido = b"A" * (20 * 1024 * 1024 + 1)

    archivo = UploadFile(
        file=BytesIO(contenido),
        filename="grande.txt"
    )

    with pytest.raises(ArchivoDemasiadoGrande):
        guardar_archivo(archivo, tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_nombre_interno_no_usa_nombre_original(tmp_path):
    archivo = UploadFile(
        file=BytesIO(b"PRUEBA"),
        filename="archivo_original.txt"
    )

    resultado = guardar_archivo(archivo, tmp_path)

    from pathlib import Path
    ruta = Path(resultado["ruta"])

    assert ruta.name != "archivo_original.txt"
    assert ruta.suffix == ".bin"
