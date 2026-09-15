"""Concilia Fase 1 - VSS parser.
Destino: CON_VSS_REPORTE + CON_VSS_DETALLE
Contrato: TXT VSS-110/115/120 multipágina
Este módulo es parte del repositorio inicial; las reglas específicas se cargan desde los mappings canónicos.
"""
from pathlib import Path
from typing import Iterable, Mapping, Any

INSUMO = 'VSS'
DESTINO = 'CON_VSS_REPORTE + CON_VSS_DETALLE'

class VssParser:
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
