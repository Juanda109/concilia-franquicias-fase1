from app.parsers.visa_ss_international import VisaSSInternationalParser
from app.parsers.vss import VSSParser
from app.parsers.mep import MEPParser
from app.parsers.pmd import PMDParser
from app.parsers.ha32 import HA32Parser
from app.parsers.ha22 import HA22Parser
from app.parsers.ha26 import HA26Parser
from app.parsers.caet import CAETParser
from app.parsers.cant import CANTParser
from app.parsers.depo import DEPOParser
from app.parsers.carta_compensacion import CartaCompensacionParser


PARSERS = {
    "HA22": HA22Parser,
    "HA26": HA26Parser,
    "HA32": HA32Parser,
    "CAET": CAETParser,
    "CANT": CANTParser,
    "PMD": PMDParser,
    "MEP": MEPParser,
    "VSS": VSSParser,
    "VISA_SS_INTERNATIONAL": VisaSSInternationalParser,
    "DEPO": DEPOParser,
    "CARTA_COMPENSACION": CartaCompensacionParser,
}


def obtener_parser(tipo_insumo: str):
    tipo = tipo_insumo.strip().upper()

    parser_class = PARSERS.get(tipo)

    if parser_class is None:
        raise ValueError(
            f"Parser no disponible para insumo: {tipo}"
        )

    return parser_class()
