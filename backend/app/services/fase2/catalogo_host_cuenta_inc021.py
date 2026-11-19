"""INC021: pares Host-cuenta autorizados para consulta diagnostica.

No implica homologacion contable ni clasificacion por franquicia.
"""

PARES_HOST_CUENTA = (
    ('HA22', '259095341'),
    ('HA32', '299095109'),
    ('HA32', '299095240'),
    ('HA32', '299095241'),
    ('HA32', '299095302'),
    ('HA22', '299095302'),
    ('HA32', '299095303'),
    ('HA32', '299095408'),
    ('HA32', '299095409'),
    ('HA22', '299095508'),
    ('HA32', '299095837'),
    ('HA32', '299095866'),
    ('HA32', '299095867'),
    ('HA32', '299095868'),
    ('HA26', '299095870'),
    ('HA32', '299095875'),
    ('HA32', '299095882'),
    ('HA32', '299095883'),
    ('HA32', '299095888'),
    ('HA26', '196095001215'),
    ('HA32', '196095001828'),
    ('HA32', '196095001829'),
    ('HA26', '196095001830'),
    ('HA22', '196095001831'),
    ('HA22', '196095001838'),
    ('HA32', '196095001838'),
    ('HA22', '196095001839'),
    ('HA32', '196095001845'),
    ('HA22', '196095001859'),
    ('HA26', '196095001919'),
    ('HA26', '196095001918'),
)

PARES_AUTORIZADOS = frozenset(PARES_HOST_CUENTA)
CUENTAS_AUTORIZADAS = frozenset(c for _, c in PARES_HOST_CUENTA)


def pares_para_cuentas(cuentas):
    """Devuelve pares autorizados; rechaza cuentas fuera del catalogo."""
    if not isinstance(cuentas, (tuple, list)) or not cuentas:
        raise ValueError('Cuentas invalidas')
    if any(not isinstance(c, str) or not c.strip() for c in cuentas):
        raise ValueError('Cuentas invalidas')
    solicitadas = {c.strip() for c in cuentas}
    desconocidas = solicitadas - CUENTAS_AUTORIZADAS
    if desconocidas:
        raise ValueError('Cuentas fuera del catalogo Host INC021: ' + ', '.join(sorted(desconocidas)))
    return tuple(par for par in PARES_HOST_CUENTA if par[1] in solicitadas)
