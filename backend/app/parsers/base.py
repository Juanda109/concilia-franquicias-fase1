from pathlib import Path
from app.ingestion.result import IngestionResult
class Parser:
    tipo_insumo: str
    def parse(self,source:Path)->IngestionResult: raise NotImplementedError
