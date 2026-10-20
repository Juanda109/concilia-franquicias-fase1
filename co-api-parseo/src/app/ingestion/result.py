from dataclasses import dataclass, field
from typing import Any

@dataclass
class RecordError:
    numero_linea: int | None
    campo: str | None
    codigo: str
    mensaje: str
    valor_origen: str | None = None

@dataclass
class IngestionResult:
    tipo_insumo: str
    records: list[dict[str,Any]] = field(default_factory=list)
    errors: list[RecordError] = field(default_factory=list)
    # A diferencia de "errors" (fatal: aborta el archivo, no se persiste nada),
    # "diagnosticos" es para anomalias por-celda que NO deben bloquear la
    # persistencia del resto de la fila/archivo (ej. PMD: una celda con error
    # de Excel se guarda en CON_ERROR_REGISTRO para trazabilidad, pero la fila
    # igual se inserta con ese campo en NULL).
    diagnosticos: list[RecordError] = field(default_factory=list)
    controls: list[dict[str,Any]] = field(default_factory=list)
