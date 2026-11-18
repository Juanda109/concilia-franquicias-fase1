"""Reglas de clasificación CAET/CANT Fase 2. No modifica Fase 1."""
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Clasificacion:
    cuenta: Optional[str]
    regla_id: Optional[str]
    motivo: str


def clasificar_cuenta(*, cod_error: str, tipo: str, canal: str, tx: str, bin_dest: str, mot_cob: str) -> Clasificacion:
    """Prioridad literal del clasificador legado: primera coincidencia gana."""
    if cod_error != "00":
        return Clasificacion(None, None, "COD_ERROR_NO_APLICABLE")
    D, P, T, B, K = tipo, canal, tx, bin_dest, mot_cob
    reglas = [
        (D=="DEBITO" and P!="CNB" and T in ("02","06"), "017-CANJE RECIBIDO TARJETA DEBITO"),
        (D=="DEBITO" and B!="404279" and P!="CNB" and T=="04", "017-ORIGINAL PAGOS A TARJETAS DEBITO"),
        (D=="DEBITO" and B=="404279" and P!="CNB" and T in ("04","22","26"), "017-ORIGINAL PAGOS A TARJETAS DEBITO"),
        (D=="DEBITO" and B not in ("404279","462550") and P!="CNB" and T in ("22","26"), "017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES"),
        (D=="DEBITO" and B=="462550" and P!="CNB" and T in ("22","26"), "017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES REGALO"),
        (D=="DEBITO" and B!="404279" and P!="CNB" and T=="24", "017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES PAGOS"),
        (D=="DEBITO" and P=="CNB", "017-OP CNBS"),
        (D=="CREDITO" and T=="16", "017-DEVOLUCION VTA NAL"),
        (T=="36", "017-REPRESENTACION  VENTA NAL (CENTRO 730)"),
        (D=="DEBITO" and T=="08", "017-ORIGINAL REEMBOLSOS DEBITO"),
        (D=="CREDITO" and T=="08", "017-ORIGINAL REEMBOLSOS CREDITO"),
        (T=="42" and B!="439467" and K not in ("15","16","03") and D in ("CREDITO","DEBITO"), "017-COMISIONES NO EXITOSAS TD Y TC IMPUTABLES BANCO"),
        (T=="42" and B!="439467" and K not in ("05","06","03") and D in ("CREDITO","DEBITO"), "017-COMISIONES NO EXITOSAS TD Y TC  TIPO 15 Y 16"),
        (D=="CREDITO" and T in ("06","02"), "017-CANJE RECIBIDO TARJETA CREDITO"),
        (D=="CREDITO" and T=="04", "017-CANJE RECIBIDO TARJETA CREDITO PAGOS"),
        (D=="CREDITO" and T=="26", "017-CANJE RECIBIDO TARJETA CREDITO REVERSION VENTAS 26 VLR. TOTAL"),
        (D=="CREDITO" and T=="22", "017-CANJE RECIBIDO TC REVERSION AVANCES 22"),
        (D=="CREDITO" and T=="24", "017-CANJE RECIBIDO TC REVERSION PAGOS 24"),
        (D=="EFIPAGO" and T not in ("Totales","56"), "017-VISA PAGOS"),
        (D=="VISA VALE" and T!="Totales", "017-CANJE  UTILIZACION VISA VALE"),
        (D=="DEBITO" and P!="CNB" and T=="32", "017-REPRESENTACION  AVANCE NAL  TD (CENTRO 730)"),
        (T=="42" and B!="439467" and K=="03" and D in ("CREDITO","DEBITO"), "017-NOTAS DEBITO CANJE RECIBIDO"),
        (T=="44" and B!="439467" and K=="03" and D in ("CREDITO","DEBITO"), "017-NOTAS CREDITO CANJE RECIBIDO"),
        (D=="CREDITO" and T=="12", "017-TP 12 DEVO AVANCE"),
    ]
    for numero, (coincide, cuenta) in enumerate(reglas, 1):
        if coincide:
            return Clasificacion(cuenta, f"F2-CANJE-CUENTA-{numero:03d}", "CLASIFICADO")
    return Clasificacion(None, None, "SIN_REGLA_FUNCIONAL")


def clasificar_comision(*, tipo: str, canal: str, tx: str, comision: Optional[int], tii: Optional[int]) -> Clasificacion:
    if tipo=="DEBITO" and canal!="CNB" and tx=="02" and comision==7450:
        return Clasificacion("017-COMISIONES EXIT. TARJETA DEBITO ONLINE", "F2-COM-001", "CLASIFICADO")
    if tipo=="CREDITO" and canal=="ELECTRONICO" and tx=="02" and comision==7450:
        return Clasificacion("017-CJE REC VISA NAL VR COM EXIT TC BATC", "F2-COM-002", "CLASIFICADO")
    if tipo=="CREDITO" and tx=="26" and tii not in (None,0):
        return Clasificacion("017-TII RECIBIDA EMISOR VISA OP REVER VENTAS", "F2-COM-003", "CLASIFICADO")
    return Clasificacion(None, None, "SIN_REGLA_FUNCIONAL")


def clasificar_regalo(*, bin_dest: str, tipo: str, canal: str, tx: str) -> Clasificacion:
    if bin_dest in ("462550","417704") and tipo=="DEBITO" and canal!="CNB" and tx in ("02","06"):
        return Clasificacion("017-CANJE RECIBIDO TARJETA DEBITO REGALO", "F2-REGALO-001", "CLASIFICADO")
    return Clasificacion(None, None, "SIN_REGLA_FUNCIONAL")
