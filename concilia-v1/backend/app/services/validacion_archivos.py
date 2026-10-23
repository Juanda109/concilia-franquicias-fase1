"""Validacion de recepcion MVP1. No cambia reglas funcionales de los parsers."""
from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from app.ingestion.registry import obtener_parser

# Solo se aplican convenciones demostradas por el codigo disponible.
PMD_NOMBRE = re.compile(r"^PMDGeneralEntidad(?:\d{6}|\d{8})(?:\s*\(\d+\))?\.(?:xls|xlsx)$", re.I)
EXTENSIONES_CONFIRMADAS = {
    "VISA_SS_INTERNATIONAL": {".pdf"},
    "PMD": {".xls", ".xlsx"},
    "MEP": {".xlsx"},
    "CARTA_COMPENSACION": {".xlsx"},
}


class ArchivoRechazado(Exception):
    def __init__(self, codigo: str, descripcion: str, errores=None):
        super().__init__(descripcion)
        self.codigo = codigo
        self.descripcion = descripcion
        self.errores = errores or []

    def detalle(self):
        return {"codigo": self.codigo, "mensaje": self.descripcion, "errores": self.errores[:20]}


def validar_archivo(tipo: str, nombre_original: str, ruta_guardada: Path):
    """Devuelve IngestionResult; no modifica la BD ni el archivo persistido.

    Se crea un directorio temporal aislado con el nombre original para parsers
    que validan source.name o source.suffix. La ruta guardada permanece opaca.
    """
    tipo = tipo.strip().upper()
    nombre = Path(nombre_original or "").name
    if not nombre or nombre in (".", "..") or "\x00" in nombre or "\\" in nombre_original or "/" in nombre_original or ":" in nombre_original:
        raise ArchivoRechazado("NOMBRE_INVALIDO", "Nombre de archivo no permitido")
    if not nombre.isascii() and any(ord(c) < 32 for c in nombre):
        raise ArchivoRechazado("NOMBRE_INVALIDO", "Nombre de archivo no permitido")
    if any(ord(c) < 32 for c in nombre):
        raise ArchivoRechazado("NOMBRE_INVALIDO", "Nombre de archivo no permitido")
    extension = Path(nombre).suffix.lower()
    if tipo in EXTENSIONES_CONFIRMADAS and extension not in EXTENSIONES_CONFIRMADAS[tipo]:
        permitidas = ", ".join(sorted(EXTENSIONES_CONFIRMADAS[tipo]))
        raise ArchivoRechazado("FORMATO_INVALIDO", f"Para {tipo} se admite: {permitidas}")
    if tipo == "PMD" and not PMD_NOMBRE.fullmatch(nombre):
        raise ArchivoRechazado("NOMBRE_INVALIDO", "Se espera PMDGeneralEntidadAAMMDD o PMDGeneralEntidadAAAAMMDD (.xls/.xlsx)")

    with tempfile.TemporaryDirectory(prefix="concilia_validacion_") as temporal:
        copia = Path(temporal) / nombre
        shutil.copyfile(ruta_guardada, copia)
        try:
            resultado = obtener_parser(tipo).parse(copia)
        except (OSError, UnicodeError, ValueError, RuntimeError, IndexError, KeyError, TypeError, EOFError) as exc:
            raise ArchivoRechazado("ESTRUCTURA_INVALIDA", f"El parser {tipo} no pudo interpretar el archivo: {type(exc).__name__}") from exc
        except Exception as exc:
            # No convertir defectos de programacion inesperados en validaciones de usuario.
            raise RuntimeError(f"Fallo inesperado del parser {tipo}") from exc

    errores = [
        {"linea": e.linea, "codigo": e.codigo, "descripcion": e.descripcion}
        for e in resultado.errors
    ]
    if errores:
        raise ArchivoRechazado("VALIDACION_FALLIDA", f"El archivo {tipo} no cumple la estructura esperada", errores)
    if not resultado.records:
        descartes_funcionales = [
            control for control in resultado.controls
            if isinstance(control, dict)
            and str(control.get("codigo", "")).startswith("DESCARTADOS_")
            and isinstance(control.get("obtenido"), int)
            and control["obtenido"] > 0
        ]

        # CAET y CANT aplican filtros funcionales de persistencia.
        # Cero registros persistibles no implica archivo fisicamente vacio.
        if tipo not in ("CAET", "CANT") or not descartes_funcionales:
            raise ArchivoRechazado(
                "SIN_REGISTROS",
                f"El archivo {tipo} no contiene registros reconocidos"
            )

    return resultado
