"""Cálculo de días hábiles con el calendario de festivos de Colombia.

Los festivos colombianos son deterministas: seis fechas fijas, siete que la Ley
Emiliani traslada al lunes siguiente, y cinco que dependen de la Pascua. Por eso
se calculan en vez de mantenerse en una tabla que habría que actualizar cada año.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

# Festivos que se celebran siempre en su fecha exacta.
_FIXED_HOLIDAYS: tuple[tuple[int, int], ...] = (
    (1, 1),    # Año Nuevo
    (5, 1),    # Día del Trabajo
    (7, 20),   # Grito de Independencia
    (8, 7),    # Batalla de Boyacá
    (12, 8),   # Inmaculada Concepción
    (12, 25),  # Navidad
)

# Festivos que la Ley Emiliani traslada al lunes siguiente.
_EMILIANI_HOLIDAYS: tuple[tuple[int, int], ...] = (
    (1, 6),    # Reyes Magos
    (3, 19),   # San José
    (6, 29),   # San Pedro y San Pablo
    (8, 15),   # Asunción de la Virgen
    (10, 12),  # Día de la Raza
    (11, 1),   # Todos los Santos
    (11, 11),  # Independencia de Cartagena
)

# Festivos derivados de la Pascua: (días desde el domingo de Pascua, ¿se traslada?).
_EASTER_HOLIDAYS: tuple[tuple[int, bool], ...] = (
    (-3, False),  # Jueves Santo
    (-2, False),  # Viernes Santo
    (39, True),   # Ascensión del Señor
    (60, True),   # Corpus Christi
    (68, True),   # Sagrado Corazón
)


def _easter_sunday(year: int) -> date:
    """Domingo de Pascua por el algoritmo gregoriano anónimo."""

    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    lunar = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lunar) // 451
    month, day = divmod(h + lunar - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _next_monday(value: date) -> date:
    """Traslado de la Ley Emiliani: el lunes siguiente, o el mismo si ya es lunes."""

    return value + timedelta(days=(7 - value.weekday()) % 7)


@lru_cache(maxsize=8)
def holidays(year: int) -> frozenset[date]:
    """Festivos colombianos del año indicado."""

    result = {date(year, month, day) for month, day in _FIXED_HOLIDAYS}
    result |= {
        _next_monday(date(year, month, day)) for month, day in _EMILIANI_HOLIDAYS
    }

    easter = _easter_sunday(year)
    for offset, moves in _EASTER_HOLIDAYS:
        holiday = easter + timedelta(days=offset)
        result.add(_next_monday(holiday) if moves else holiday)

    return frozenset(result)


def is_business_day(value: date) -> bool:
    """True si es día hábil: lunes a viernes y no festivo."""

    return value.weekday() < 5 and value not in holidays(value.year)


def business_days_between(start: date, end: date) -> int:
    """Días hábiles transcurridos entre ``start`` (excluido) y ``end`` (incluido).

    Devuelve 0 cuando ``end`` no es posterior a ``start``, de modo que una fecha
    futura nunca aparente haber cumplido el plazo de conciliación.
    """

    if end <= start:
        return 0

    total = 0
    current = start + timedelta(days=1)
    while current <= end:
        if is_business_day(current):
            total += 1
        current += timedelta(days=1)
    return total
