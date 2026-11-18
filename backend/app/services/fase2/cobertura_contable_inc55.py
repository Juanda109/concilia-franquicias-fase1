"""INC55: modelo puro de cobertura contable; NO realiza escrituras."""
from __future__ import annotations
from dataclasses import dataclass, replace
from datetime import date
from typing import Iterable

FUENTES = frozenset({'HA22','HA26','HA32'})
TIPOS = frozenset({'MOVIMIENTOS','SALDO_CIERRE','SALDO_REFERENCIA'})
ESTADOS = frozenset({'PENDIENTE','EN_PROCESO','PROCESADO','CONFIRMADO','FALLIDO'})
TRANSICIONES = {
    'PENDIENTE': frozenset({'EN_PROCESO'}),
    'EN_PROCESO': frozenset({'PROCESADO','FALLIDO'}),
    'PROCESADO': frozenset({'CONFIRMADO','FALLIDO'}),
    'FALLIDO': frozenset({'EN_PROCESO'}),
    'CONFIRMADO': frozenset(),
}
@dataclass(frozen=True)
class CoberturaContable:
    fecha: date
    fuente: str
    cuenta: str
    centro: str
    tipo_consulta: str
    estado: str = 'PENDIENTE'
    id_archivo: int | None = None
    evidencia_cierre: str | None = None
    referencia: str | None = None

    def __post_init__(self):
        if self.fuente not in FUENTES or self.tipo_consulta not in TIPOS or self.estado not in ESTADOS:
            raise ValueError('Fuente, tipo o estado invalido')
        if not self.cuenta or not self.centro:
            raise ValueError('Cuenta y centro obligatorios')
        if self.tipo_consulta == 'SALDO_REFERENCIA' and not self.referencia:
            raise ValueError('Referencia contable no validada')
        if self.estado == 'CONFIRMADO' and not self.evidencia_cierre:
            raise ValueError('Confirmacion requiere evidencia de cierre')

    @property
    def clave(self):
        return (self.fecha, self.fuente, self.cuenta, self.centro, self.tipo_consulta, self.referencia or '')

def transicionar(c: CoberturaContable, destino: str, *, evidencia_cierre: str | None = None):
    if destino not in TRANSICIONES[c.estado]:
        raise ValueError('Transicion no permitida')
    if destino == 'CONFIRMADO' and not (evidencia_cierre and evidencia_cierre.strip()):
        raise ValueError('No se confirma solo por procesar archivo')
    return replace(c, estado=destino, evidencia_cierre=evidencia_cierre if destino == 'CONFIRMADO' else c.evidencia_cierre)

def evaluar_cobertura(registros: Iterable[CoberturaContable]):
    """Fail closed: duplicados contradictorios no se consideran confirmados."""
    por_clave = {}
    for c in registros:
        anterior = por_clave.get(c.clave)
        if anterior is not None and anterior != c:
            raise ValueError('Coberturas contradictorias')
        por_clave[c.clave] = c
    return {'total': len(por_clave), 'confirmados': sum(c.estado == 'CONFIRMADO' for c in por_clave.values()),
            'pendientes': [c.clave for c in por_clave.values() if c.estado != 'CONFIRMADO']}
