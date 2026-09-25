from pathlib import Path
from app.parsers.ha22 import HA22Parser
from app.parsers.ha26 import HA26Parser
from app.parsers.ha32 import HA32Parser
from app.parsers.pmd import PMDParser
from app.parsers.mep import MEPParser
from app.parsers.vss import VSSParser
from app.parsers.carta_cei240a import CartaCEI240AParser

def run():
 cases=[
  (HA22Parser(),Path("/mnt/data/DESCARHA22_F260914(2).TXT"),9),
  (HA26Parser(),Path("/mnt/data/DESCARHA26_F260914(2).TXT"),4),
  (HA32Parser(),Path("/mnt/data/DESCARHA32_F260914(2).TXT"),19),
  (PMDParser(),Path("/mnt/data/PMDDetalleTransacciones20260702(1).xlsx"),5),
  (MEPParser(),Path("/mnt/data/MEP(1).xlsx"),2),
  (VSSParser(),Path("/mnt/data/VSS BBVA 02 JULIO(4).txt"),4),
  (CartaCEI240AParser(),Path("/mnt/data/090926(3).xlsx"),7),
 ]
 for parser,path,expected in cases:
  result=parser.parse(path)
  assert not result.errors,(parser.tipo_insumo,result.errors)
  assert len(result.records)==expected,(parser.tipo_insumo,len(result.records),expected)
 return len(cases)
if __name__=="__main__": print(run())
