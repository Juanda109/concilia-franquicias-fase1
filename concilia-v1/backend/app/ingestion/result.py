from dataclasses import dataclass, field
from typing import Any


@dataclass
class RecordError:
    linea: int | None
    referencia: str | None
    codigo: str
    descripcion: str


@dataclass
class IngestionResult:
    tipo_insumo: str
    records: list[Any] = field(default_factory=list)
    errors: list[RecordError] = field(default_factory=list)
    controls: list[Any] = field(default_factory=list)
