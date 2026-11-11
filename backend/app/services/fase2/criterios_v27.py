"""Criterios funcionales suministrados por usuario; NO son resultados PostgreSQL."""
from decimal import Decimal
from dataclasses import dataclass

@dataclass(frozen=True)
class Caso:
    cuenta: str
    valor_franquicia: str
    host: str
    rechazos: str | None
    diferencia: str | None
    estado: str

CASOS = (
    Caso('299095302','1260','1260','0','0','CONCILIADO'),
    Caso('299095408','1260','1440','180',None,'CONCILIO_CON_DIFERENCIA'),
    Caso('299095409','1440','1530','0','90','NO_CONCILIA'),
    Caso('196095001215','0','2520',None,None,'NO_CONCILIA'),
    Caso('196095001830','0','2790',None,None,'NO_CONCILIA'),
    Caso('196095001838','0','2970',None,None,'NO_CONCILIA'),
    Caso('196095001839','0','3060',None,None,'NO_CONCILIA'),
    Caso('196095001859','0','3240',None,None,'NO_CONCILIA'),
    Caso('196095001918','0','3330',None,None,'NO_CONCILIA'),
    Caso('299095882','0','2250',None,None,'NO_CONCILIA'),
)

def validar_criterios(casos=CASOS):
    assert len(casos)==10 and len({c.cuenta for c in casos})==10
    for c in casos:
        assert Decimal(c.valor_franquicia)>=0
        assert Decimal(c.host)>=0
        if c.rechazos is not None: assert Decimal(c.rechazos)>=0
    assert Decimal(casos[0].valor_franquicia)==Decimal(casos[0].host)
    assert Decimal(casos[2].host)-Decimal(casos[2].valor_franquicia)==Decimal(casos[2].diferencia)
    assert Decimal(casos[1].host)-Decimal(casos[1].valor_franquicia)==Decimal(casos[1].rechazos)
    return True

def generar_criterios():
    validar_criterios()
    return {'modo':'CRITERIOS_ACEPTACION_NO_CALCULADOS', 'certificado':False,
            'origen':'TABLA_PROPORCIONADA_POR_USUARIO',
            'advertencia':'No corresponde a resultados persistidos ni homologaciones aprobadas.',
            'filas':[c.__dict__ for c in CASOS]}
