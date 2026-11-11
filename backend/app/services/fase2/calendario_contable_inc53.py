"""INC53: calendario Colombia y planificación Host. Sin operaciones de BD."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Callable, Iterable

class TipoConsulta(str, Enum):
    MOVIMIENTOS = 'DETALLE_MOVIMIENTOS'
    SALDO = 'SALDO_ANTERIOR'
    REFERENCIA = 'SALDO_REFERENCIA'

@dataclass(frozen=True)
class Configuracion:
    cuenta: str
    centro: str
    tipo: TipoConsulta
    desfase_habiles: int = 1
    referencia: str | None = None

@dataclass(frozen=True)
class PlanConsulta:
    cuenta: str
    centro: str
    tipo: TipoConsulta
    ejecucion: date
    fechas_pendientes: tuple[date, ...]
    desde: date | None
    hasta: date | None
    corte_saldo: date | None
    estado: str


def domingo_pascua(anio: int) -> date:
    a = anio % 19; b = anio // 100; c = anio % 100
    d = b // 4; e = b % 4; f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19*a + b - d - g + 15) % 30
    i = c // 4; k = c % 4; l = (32 + 2*e + 2*i - h - k) % 7
    m = (a + 11*h + 22*l) // 451
    mes = (h + l - 7*m + 114) // 31
    dia = ((h + l - 7*m + 114) % 31) + 1
    return date(anio, mes, dia)


def siguiente_lunes(fecha: date) -> date:
    return fecha + timedelta(days=(7-fecha.weekday()) % 7)


def festivos_colombia(anio: int) -> frozenset[date]:
    """Festivos nacionales legales; cierres bancarios extra se inyectan aparte."""
    pascua = domingo_pascua(anio)
    fijos = [(1,1),(5,1),(7,20),(8,7),(12,8),(12,25)]
    trasladables = [(1,6),(3,19),(6,29),(8,15),(10,12),(11,1),(11,11)]
    festivos = {date(anio,m,d) for m,d in fijos}
    festivos.update(siguiente_lunes(date(anio,m,d)) for m,d in trasladables)
    festivos.update((pascua-timedelta(days=3),pascua-timedelta(days=2)))
    festivos.update(siguiente_lunes(pascua+timedelta(days=n)) for n in (39,60,68))
    return frozenset(festivos)


class CalendarioColombia:
    def __init__(self, cierres_extra: Iterable[date] = ()):
        self.cierres_extra = frozenset(cierres_extra)

    def habil(self, fecha: date) -> bool:
        return fecha.weekday() < 5 and fecha not in festivos_colombia(fecha.year) and fecha not in self.cierres_extra

    def retroceder_habiles(self, fecha: date, cantidad: int) -> date:
        if cantidad < 1:
            raise ValueError('desfase debe ser positivo')
        actual = fecha
        for _ in range(cantidad):
            actual -= timedelta(days=1)
            while not self.habil(actual):
                actual -= timedelta(days=1)
        return actual


def planificar(config: Configuracion, ejecucion: date, fechas_pendientes: Iterable[date],
              calendario: CalendarioColombia) -> PlanConsulta:
    """Fechas pendientes provienen del ledger de cierres, no se infieren de éxito de consulta.

    La selección del corte para saldos requiere confirmación de negocio y no suma saldos.
    """
    if not calendario.habil(ejecucion):
        raise ValueError('Host solo se ejecuta en día hábil colombiano')
    if config.desfase_habiles < 1:
        raise ValueError('desfase inválido')
    if config.tipo == TipoConsulta.REFERENCIA and not config.referencia:
        return PlanConsulta(config.cuenta,config.centro,config.tipo,ejecucion,(),None,None,None,'PENDIENTE_REFERENCIA')
    pendientes = tuple(sorted(set(d for d in fechas_pendientes if d < ejecucion)))
    if config.tipo == TipoConsulta.MOVIMIENTOS:
        return PlanConsulta(config.cuenta,config.centro,config.tipo,ejecucion,pendientes,
                            pendientes[0] if pendientes else None,
                            pendientes[-1] if pendientes else None,None,
                            'PENDIENTE_COBERTURA' if pendientes else 'SIN_PENDIENTES')
    corte = calendario.retroceder_habiles(ejecucion,config.desfase_habiles)
    return PlanConsulta(config.cuenta,config.centro,config.tipo,ejecucion,pendientes,None,None,corte,
                        'PENDIENTE_VALIDACION_CORTE' if pendientes else 'SIN_PENDIENTES')


def claves_movimientos_unicas(movimientos: Iterable[dict]) -> list[dict]:
    """Deduplicación de lectura por procedencia; nunca fusiona cuentas/fuentes distintas."""
    vistos = set(); resultado = []
    for m in movimientos:
        clave = (m['fuente'],m['id_archivo'],m['linea_origen'])
        if clave in vistos:
            continue
        vistos.add(clave); resultado.append(m)
    return resultado
