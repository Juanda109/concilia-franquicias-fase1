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
    controls: list[dict[str,Any]] = field(default_factory=list)
