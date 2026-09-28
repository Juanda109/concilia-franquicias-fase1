from pathlib import Path
from app.parsers.base import Parser
from app.ingestion.result import IngestionResult,RecordError
import re
class VSSParser(Parser):
 tipo_insumo="VSS"
 def parse(self,source:Path):
  r=IngestionResult(self.tipo_insumo); text=source.read_text(encoding="utf-8",errors="replace")
  pages=[p for p in text.split("\f") if p.strip()]
  for p in pages:
   rid=re.search(r"REPORT ID:\s*(VSS-\d+)",p); page=re.search(r"PAGE:\s*(\d+)",p)
   settle=re.search(r"SETTLEMENT CURRENCY:\s*([A-Z]{3})",p); clear=re.search(r"CLEARING CURRENCY:\s*([A-Z]{3})",p)
   if not rid: r.errors.append(RecordError(None,None,"REPORT_ID_AUSENTE","Página sin REPORT ID")); continue
   r.records.append({"report_id":rid.group(1),"numero_pagina":int(page.group(1)) if page else None,
                     "settlement_currency":settle.group(1) if settle else None,"clearing_currency":clear.group(1) if clear else None})
  a=re.search(r"NET SETTLEMENT AMOUNT\s+[\d,]+\.\d{2}\s+[\d,]+\.\d{2}\s+([\d,]+\.\d{2})(CR|DB)",text)
  b=re.search(r"FINAL SETTLEMENT NET AMOUNT\s+([\d,]+\.\d{2})(CR|DB)",text)
  if a and b:r.controls.append({"codigo":"VSS_110_115_NET","estado":"OK" if a.groups()==b.groups() else "ERROR","vss110":"".join(a.groups()),"vss115":"".join(b.groups())})
  return r
