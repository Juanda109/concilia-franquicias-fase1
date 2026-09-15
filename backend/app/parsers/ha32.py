import csv
from pathlib import Path
from app.parsers.base import Parser
from app.ingestion.result import IngestionResult, RecordError

class HA32Parser(Parser):
    tipo_insumo="HA32"
    expected_columns=10
    def parse(self,source:Path):
        result=IngestionResult(self.tipo_insumo)
        with source.open(encoding="utf-8-sig",errors="strict",newline="") as f:
            reader=csv.DictReader(f,delimiter="|")
            if len(reader.fieldnames or []) != self.expected_columns:
                result.errors.append(RecordError(1,None,"HEADER_INVALIDO",f"Se esperaban {self.expected_columns} columnas"))
                return result
            for n,row in enumerate(reader,start=2):
                result.records.append({"numero_linea":n,**{k:(v.strip() if isinstance(v,str) else v) for k,v in row.items()}})
        result.controls.append({"codigo":"TOTAL_REGISTROS","obtenido":len(result.records)})
        return result
