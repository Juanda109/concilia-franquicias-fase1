"""Clasificacion funcional de cuentas por franquicia, version V39.
No establece reglas monetarias ni certifica conciliaciones.
"""
from collections import Counter

CUENTAS_POR_FRANQUICIA = {
    'VISA': ('259095341', '299095888', '299095303'),
    'CREDIBANCO': ('299095302', '299095408', '299095409', '196095001215', '196095001830', '196095001838', '196095001839', '196095001859', '196095001918', '299095882', '299095301', '299095300', '299095880'),
    'REDEBAN': ('196095001828', '196095001829', '196095001831', '196095001845', '196095001919', '299095109', '299095240', '299095241', '299095508', '299095837', '299095866', '299095867', '299095868', '299095870', '299095875', '299095883'),
}
CUENTA_A_FRANQUICIA = {cuenta: franquicia for franquicia, cuentas in CUENTAS_POR_FRANQUICIA.items() for cuenta in cuentas}
if len(CUENTA_A_FRANQUICIA) != 32 or sum(map(len, CUENTAS_POR_FRANQUICIA.values())) != 32:
    raise RuntimeError('Clasificacion V39 inconsistente')

def clasificar_cuenta(cuenta):
    return CUENTA_A_FRANQUICIA.get(str(cuenta).strip()) if cuenta is not None else None

def enriquecer_cobertura(cobertura):
    """No altera las evidencias Host ni las homologaciones existentes."""
    return [{**fila, 'franquicia_catalogo_v39': clasificar_cuenta(fila.get('cuenta')),
             'clasificacion_v39_certificada': False} for fila in cobertura]

def resumen_catalogo():
    return {franquicia: len(cuentas) for franquicia, cuentas in CUENTAS_POR_FRANQUICIA.items()}
