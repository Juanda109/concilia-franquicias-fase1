"""Incremento 37: evaluación controlada de fórmulas verificadas de Plantilla Maestra.
No infiere correspondencias, no modifica base de datos y no certifica conciliación.
"""
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from typing import Mapping, Sequence

class InsumoPendiente(ValueError):
    pass

@dataclass(frozen=True)
class ResultadoRegla:
    regla: str
    cuenta: str
    celda: str
    formula_excel: str
    valor: Decimal
    certificado: bool = False
    estado: str = "CALCULADO_NO_HOMOLOGADO"

def _d(valor, nombre):
    if valor is None or isinstance(valor, bool):
        raise InsumoPendiente(f"Falta valor numérico: {nombre}")
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        raise InsumoPendiente(f"Valor no numérico: {nombre}")
    if not d.is_finite():
        raise InsumoPendiente(f"Valor no finito: {nombre}")
    return d

def calcular(regla: str, celdas: Mapping[str, object], carta: Sequence[Mapping[str, object]] | None = None) -> ResultadoRegla:
    """Ejecuta solo fórmulas literales contrastadas; no evalúa expresiones arbitrarias."""
    r = regla.upper()
    def v(ref): return _d(celdas.get(ref), ref)
    if r == "PM37-O15":
        valor=v("M15")+v("N15")
        return ResultadoRegla(r,"196095001857","O15","=+M15+N15",valor)
    if r == "PM37-P15":
        valor=v("L15")-v("O15")
        return ResultadoRegla(r,"196095001857","P15","=+(L15)-O15",valor)
    if r == "PM37-O26":
        valor=v("M26")+v("N26")
        return ResultadoRegla(r,"196095001861","O26","=SUM(M26:N26)",valor)
    if r == "PM37-P26":
        valor=v("L26")-v("O26")
        return ResultadoRegla(r,"196095001861","P26","=+(L26)-O26",valor)
    if r == "PM37-M29":
        valor=v("M28")-v("M26")
        return ResultadoRegla(r,"196095001221","M29","=+M28-M26",valor)
    if r == "PM37-P29":
        valor=sum((v(f"P{i}") for i in range(15,27)),Decimal(0))
        return ResultadoRegla(r,"196095001221","P29","=SUM(P15:P26)",valor)
    if r in {"PM37-G38","PM37-G39","PM37-G41"}:
        if carta is None:
            raise InsumoPendiente("Falta evidencia CARTA externa")
        col={"PM37-G38":"D","PM37-G39":"E","PM37-G41":"G"}[r]
        cuenta={"D":"419595021","E":"519030008","G":"419595022"}[col]
        celda={"D":"G38","E":"G39","G":"G41"}[col]
        etiqueta="     T O T A L E S   A   F A V O R"
        valor=Decimal(0)
        for n,fila in enumerate(carta,1):
            if str(fila.get("B", "")) == etiqueta:
                valor+=_d(fila.get(col),f"CARTA fila {n} col {col}")
        return ResultadoRegla(r,cuenta,celda,f'=SUMIF([1]CARTA!$B$1:$B$1048576,"{etiqueta}",[1]CARTA!${col}$1:${col}$1048576)',valor)
    if r in {"PM37-F42","PM37-G42"}:
        col="F" if r.endswith("F42") else "G"
        valor=sum((v(f"{col}{i}") for i in range(6,42)),Decimal(0))
        return ResultadoRegla(r,"TOTALCANJ",f"{col}42",f"=SUM({col}6:{col}41)",valor)
    raise KeyError(f"Regla no autorizada: {regla}")
