from app.parsers.ha22 import HA22Parser
from app.parsers.ha26 import HA26Parser
from app.parsers.ha32 import HA32Parser
from app.parsers.canje import CanjeParser
from app.parsers.depo import DEPOParser
from app.parsers.carta_cei240a import CartaCEI240AParser
from app.parsers.pmd import PMDParser
from app.parsers.mep import MEPParser
from app.parsers.vss import VSSParser
PARSERS={"HA22":HA22Parser(),"HA26":HA26Parser(),"HA32":HA32Parser(),"CAET":CanjeParser("CAET"),"CANT":CanjeParser("CANT"),
"DEPO":DEPOParser(),"CARTA_COMPENSACION":CartaCEI240AParser(),"PMD":PMDParser(),"MEP":MEPParser(),"VSS":VSSParser()}
def get_parser(tipo):
    if tipo not in PARSERS: raise KeyError(f"Parser no implementado todavía: {tipo}")
    return PARSERS[tipo]
