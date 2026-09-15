"""Concilia Fase 1 - PMD parser.
Destino: CON_PMD_RESULTADO
Contrato: Excel PMD_Detalle 21 columnas
Este módulo es parte del repositorio inicial; las reglas específicas se cargan desde los mappings canónicos.
"""
from pathlib import Path
from typing import Iterable, Mapping, Any

INSUMO = 'PMD'
DESTINO = 'CON_PMD_RESULTADO'

class PmdParser:
    insumo = INSUMO
    destino = DESTINO

    def validate(self, source: Path) -> None:
        if not source.exists():
            raise FileNotFoundError(source)
        if source.stat().st_size == 0:
            raise ValueError(f"{INSUMO}: archivo vacío")

    def parse(self, source: Path) -> Iterable[Mapping[str, Any]]:
        self.validate(source)
        raise NotImplementedError("Implementar usando mapping canónico incluido en components/config.")
