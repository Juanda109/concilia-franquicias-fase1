"""Interpretacion de archivos conservando el nombre original."""

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil

from app.ingestion.registry import obtener_parser


@contextmanager
def archivo_con_nombre_original(fisico, nombre_original):
    fisico = Path(fisico)
    nombre = Path(nombre_original).name

    if (
        not nombre_original
        or nombre in ("", ".", "..")
        or "/" in nombre_original
        or "\\" in nombre_original
        or "\x00" in nombre_original
    ):
        raise ValueError("Nombre original invalido")

    if not fisico.is_file():
        raise FileNotFoundError(fisico)

    with TemporaryDirectory(prefix="concilia_parser_") as carpeta:
        temporal = Path(carpeta) / nombre
        shutil.copyfile(fisico, temporal)
        yield temporal


def interpretar_archivo(tipo, fisico, nombre_original):
    """Interpreta sin modificar el archivo almacenado."""

    if tipo in ("PMD", "MEP", "VISA_SS_INTERNATIONAL"):
        with archivo_con_nombre_original(
            fisico, nombre_original
        ) as temporal:
            return obtener_parser(tipo).parse(temporal)

    return obtener_parser(tipo).parse(Path(fisico))
