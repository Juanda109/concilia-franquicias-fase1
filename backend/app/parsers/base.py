from abc import ABC, abstractmethod
from pathlib import Path

from app.ingestion.result import IngestionResult


class Parser(ABC):
    tipo_insumo: str = ""

    @abstractmethod
    def parse(self, source: Path) -> IngestionResult:
        """Procesa un archivo de entrada."""
        raise NotImplementedError
