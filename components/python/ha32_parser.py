"""Parser productivo base HA32: archivo pipe-delimited con header."""
from pathlib import Path
import csv
INSUMO='HA32'
EXPECTED_COLUMNS=10
DESTINO='CON_HA32_RESULTADO'

class HA32Parser:
    def validate(self, source: Path):
        if not source.exists() or source.stat().st_size==0: raise ValueError(f"{INSUMO} archivo inexistente/vacío")
    def parse(self, source: Path):
        self.validate(source)
        with source.open(encoding="utf-8-sig",errors="strict",newline="") as f:
            reader=csv.DictReader(f,delimiter="|")
            if len(reader.fieldnames or []) != EXPECTED_COLUMNS:
                raise ValueError(f"{INSUMO} header inválido: {len(reader.fieldnames or [])} columnas")
            for line,row in enumerate(reader,start=2):
                yield {"numeroLinea":line, **{k:(v.strip() if isinstance(v,str) else v) for k,v in row.items()}}
