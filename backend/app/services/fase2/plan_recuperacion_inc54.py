"""INC54: planificacion segura de cobertura Host; no ejecuta descargas ni escrituras."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable
from app.services.fase2.calendario_contable_inc53 import CalendarioColombia

FUENTES = frozenset(('HA22', 'HA26', 'HA32'))

@dataclass(frozen=True)
class Cobertura:
    fecha: date
    fuente: str
    estado: str  # CONFIRMADA, PENDIENTE, FALLIDA, EN_PROCESO


def planificar_recuperacion(*, ejecucion: date, desde: date, coberturas: Iterable[Cobertura],
                            calendario: CalendarioColombia, hasta: date | None = None) -> dict:
    """Devuelve pendientes por fecha/fuente, sin asumir cobertura por presencia de archivos.

    Solo CONFIRMADA prueba cierre. Se requiere una fecha desde explicita, evitando
    inferir un ultimo cierre a partir de registros parciales.
    """
    if not calendario.habil(ejecucion):
        raise ValueError('La ejecucion debe ocurrir en dia habil colombiano')
    fin = hasta or (ejecucion - timedelta(days=1))
    if desde > fin or fin >= ejecucion:
        raise ValueError('Intervalo de recuperacion invalido')
    estados = {}
    for c in coberturas:
        if c.fuente not in FUENTES:
            raise ValueError('Fuente Host desconocida')
        if c.estado not in ('CONFIRMADA', 'PENDIENTE', 'FALLIDA', 'EN_PROCESO'):
            raise ValueError('Estado de cobertura desconocido')
        clave = (c.fecha, c.fuente)
        if clave in estados and estados[clave] != c.estado:
            raise ValueError('Coberturas contradictorias: ' + str(clave))
        estados[clave] = c.estado
    faltantes = []
    fecha = desde
    while fecha <= fin:
        for fuente in sorted(FUENTES):
            estado = estados.get((fecha, fuente), 'SIN_EVIDENCIA')
            if estado != 'CONFIRMADA':
                faltantes.append({'fecha': fecha.isoformat(), 'fuente': fuente,
                                  'estado': estado, 'habil': calendario.habil(fecha)})
        fecha += timedelta(days=1)
    return {'ejecucion': ejecucion.isoformat(), 'desde': desde.isoformat(),
            'hasta': fin.isoformat(), 'pendientes': faltantes,
            'estado': 'PENDIENTE_VALIDACION_COBERTURA' if faltantes else 'COBERTURA_CONFIRMADA',
            'ejecucion_automatica_habilitada': False}
