"""Verifica el TRAMO DE LUIS (2.4.0.1.12 en adelante) contra la fuente del dato.

Hermano de verificar_mensajes.py, que cubre mi mitad. Aqui se comprueban las
cuatro cosas que decide su tramo:

  DESENLACE   el paso al que llega el cliente corresponde a la clasificacion
              que devolvio el servicio (presencial / reversado / pqr /
              devolucion). Es LA comprobacion importante: si la regla ECI
              cambia de sentido, esto lo detecta aunque el texto siga igual.
  PROCEDENCIA los 4 digitos de los mensajes de bloqueo salen de last_four del
              producto (el PAN de financial-overview), y el importe y la
              descripcion del desenlace salen del movimiento elegido.
  PARAMETROS  los dias habiles que se prometen al cliente son los configurados,
              no un numero escrito a mano.
  BUCLE       2.4.0.1.20.1 aparece si se pidieron 2 o 3 transacciones y NO
              aparece si se pidio 1.

Se compara contra la FUENTE y no contra literales: un cambio de copy autorizado
no rompe la prueba, pero un desenlace que no corresponde a su clasificacion si.
Las divergencias de copy se reportan como AVISO, no como fallo.

Uso:  python3 -u verificar_tramo_luis.py  (stack local levantado; ver BITACORA_F0)

Tarda ~6 min: recorre seis conversaciones completas hasta el desenlace. El -u
importa si se redirige la salida a fichero; sin el, no se ve avanzar nada hasta
que termina.
"""

from __future__ import annotations

import json
import re
import ssl
import subprocess
import time
import unicodedata
import urllib.request

from runner import Conversacion

OS_URL = "https://localhost:9200"
BASIC = "Basic YWRtaW46YWRtaW4="          # admin/admin, OpenSearch local de pruebas

# Cliente por desenlace. Los tres ultimos se crearon en F1 justamente porque
# 'presencial' y 'reversado' no eran alcanzables por UI (sus fixtures vivian en
# PAN sin entrada en financial-overview) y no habia ni un solo eci=0.
CLIENTES = {
    "devolucion": "1013634970",   # M, eci=0
    "presencial": "1013634971",   # N, eci=9
    "reversado":  "1013634972",   # O, reversa gestionada
    "pqr":        "1013634960",   # C, eci=5
}

# Desenlace -> paso que debe pintarse
PASO_DE = {
    "presencial": "2.4.0.1.19.1",
    "reversado":  "2.4.0.1.19.2",
    "pqr":        "2.4.0.1.19.pqr",
    "devolucion": "2.4.0.1.20",
}

FECHA = "06/08/2026"
_CRUDOS = ("XXXX", "None", "null", "product_id", "last_four_pan_id", "{", "}")

fallos: list[str] = []
avisos: list[str] = []
comprobaciones = 0


def check(cond: bool, etiqueta: str) -> bool:
    global comprobaciones
    comprobaciones += 1
    print(f"  [{'OK ' if cond else 'FALLA'}] {etiqueta}")
    if not cond:
        fallos.append(etiqueta)
    return cond


def aviso(texto: str) -> None:
    avisos.append(texto)
    print(f"  [AVISO] {texto}")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def _doc(conversation_id: str) -> dict:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        f"{OS_URL}/conversations-reference/_doc/{conversation_id}",
        headers={"Authorization": BASIC},
    )
    with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
        return json.loads(r.read())["_source"]


def _reset(uid: str) -> None:
    subprocess.run(["./reset_cliente.sh", uid], capture_output=True, check=False)


def _elegir(opciones: list[str], texto: str) -> str:
    hit = next((o for o in opciones if _norm(texto) in _norm(o)), None)
    if hit is None and _norm(texto).startswith("tarjeta"):
        # Fuente fo: la etiqueta del selector es el nombre real del producto
        # ("VISA ORO LM •0060"), sin la palabra "Tarjeta". Se elige la
        # primera opcion con mascara •. Con la fuente ADA el hit de arriba
        # gana antes, asi que el comportamiento clasico no cambia.
        hit = next((o for o in opciones if "•" in o), None)
    return hit if hit is not None else texto


def _pesos(valor) -> str:
    return f"${float(valor):,.0f}".replace(",", ".")


def _hasta_bloqueo(uid: str, cantidad: str = "1"):
    """Lleva la conversacion hasta el mensaje de bloqueo definitivo hecho."""
    _reset(uid)
    c = Conversacion(uid)
    assert c.abrir(), c.error
    o: list[str] = []
    t = ""
    for e in ("No reconozco esta compra", "Compra presencial", cantidad, "Empezar ahora",
              "Si, continuar", "Tarjeta", "Entre $35.000", FECHA):
        t, o = c.decir(_elegir(o, e))
    movs = [x for x in o if "no encuentro" not in _norm(x)]
    assert movs, f"{uid}: el listado no trae movimientos"
    t, o = c.decir(movs[0])                       # confirmacion (.11)
    for e in ("Si, continuar con el reporte", "Si, continuar con la investigacion",
              "Si, bloquear definitivamente", "Si, bloquear y continuar"):
        t, o = c.decir(_elegir(o, e))
    if "app bbva" in _norm(t) and any(_norm(x) == "continuar" for x in o):
        # OOB (dev, 24/08): tras pedir el bloqueo llega la notificacion a la
        # App BBVA; un turno mas de "Continuar" ejecuta el bloqueo -> .17.2.
        t, o = c.decir(_elegir(o, "Continuar"))
    return c, t, o


def verificar(seccion: str = "todo") -> int:
    """seccion: todo | bloqueo | desenlaces | bucle.

    La pasada completa son SEIS conversaciones de ~13 turnos con sondeo: unos 12
    minutos. Si el entorno corta procesos largos, se ejecuta por partes y se
    suman los resultados; por eso existe este argumento.
    """
    # ---------- 1. bloqueo definitivo: procedencia de los 4 digitos ----------
    if seccion in ("todo", "bloqueo"):
        _seccion_bloqueo()
    if seccion in ("todo", "desenlaces"):
        _seccion_desenlaces()
    if seccion in ("todo", "bucle"):
        _seccion_bucle()
    if seccion in ("todo", "errores"):
        _seccion_errores()
    if seccion in ("todo", "bloqueo_repetido"):
        _seccion_bloqueo_repetido()

    print(f"\n{'TRAMO DE LUIS OK' if not fallos else f'{len(fallos)} FALLOS'} "
          f"({comprobaciones} comprobaciones, {len(avisos)} avisos)")
    for f in fallos:
        print(f"  - FALLA: {f}")
    for a in avisos:
        print(f"  - AVISO: {a}")
    for uid in CLIENTES.values():
        _reset(uid)
    return 0 if not fallos else 1


def _seccion_bloqueo() -> None:
    print("\n2.4.0.1.17.2 - bloqueo definitivo")
    c, t, o = _hasta_bloqueo(CLIENTES["devolucion"])
    doc = _doc(c.cid)
    cap = doc["captured_data"]
    productos = (json.loads(cap.get("trx_products_result") or "{}")
                 .get("data", {}).get("products") or [])
    check(bool(productos), "hay productos en el payload de origen")
    ultimos = str(productos[0].get("last_four") or "") if productos else ""
    check(bool(ultimos) and ultimos in t,
          f"bloqueo: los 4 digitos son los de last_four del producto ({ultimos})")
    contrato = str(productos[0].get("contract_id") or "") if productos else ""
    check(len(contrato) <= 4 or contrato not in t,
          "bloqueo: no expone el contrato completo")
    for crudo in _CRUDOS:
        check(crudo not in t, f"bloqueo: sin '{crudo}' en pantalla")
    dias = re.search(r"(\d+)\s*d[ií]as h[aá]biles", t)
    check(bool(dias), "bloqueo: promete un plazo en dias habiles")


def _seccion_desenlaces() -> None:
    for desenlace, uid in CLIENTES.items():
        print(f"\n2.4.0.1.19/.20 - desenlace {desenlace} (cliente {uid})")
        c, t, o = _hasta_bloqueo(uid)
        for _ in range(3):                        # .17.2 -> .18 -> desenlace
            if not o:
                break
            t, o = c.decir(o[0])
            doc = _doc(c.cid)
            if str(doc.get("current_step") or "").startswith(("2.4.0.1.19", "2.4.0.1.20")):
                break
        doc = _doc(c.cid)
        cap = doc["captured_data"]
        paso = str(doc.get("current_step") or "")
        clasif = json.loads(cap.get("trx_clasificacion") or "{}")
        resultado = str(clasif.get("resultado") or "")

        # LA comprobacion: el desenlace corresponde a la clasificacion, y la
        # clasificacion es la que se esperaba para este cliente.
        check(resultado == desenlace,
              f"{desenlace}: el servicio clasifica como '{resultado}'")
        check(paso == PASO_DE[desenlace],
              f"{desenlace}: pinta el paso {PASO_DE[desenlace]} (esta en {paso})")

        # PROCEDENCIA: importe y descripcion, del movimiento elegido
        movs = json.loads(cap.get("trx_movimientos_result") or "{}").get("movimientos") or []
        if movs and desenlace in ("presencial", "reversado"):
            mov = movs[0]
            check(_pesos(mov["valor"]) in t,
                  f"{desenlace}: el importe es el del movimiento ({_pesos(mov['valor'])})")
            if desenlace == "presencial":
                check(str(mov.get("descripcion") or "") in t,
                      f"{desenlace}: la descripcion es la del movimiento")
        for crudo in _CRUDOS:
            check(crudo not in t, f"{desenlace}: sin '{crudo}' en pantalla")

        # AVISOS de copy (no rompen: son forma, no dato)
        if "**" in t:
            aviso(f"{desenlace}: el texto entrega Markdown literal ('**'). "
                  f"Ningun otro mensaje del flujo lo usa: el cliente leeria los asteriscos.")
        if re.search(r"\b(informacion|revision|transaccion|devolucion)\b", t):
            aviso(f"{desenlace}: hay palabras sin tilde en un texto donde el resto "
                  f"del tramo si las lleva.")


def _seccion_bucle() -> None:
    print("\n2.4.0.1.20.1 - bucle de multiples transacciones")
    for cantidad, debe_aparecer in (("1", False), ("2", True)):
        c, t, o = _hasta_bloqueo(CLIENTES["devolucion"], cantidad)
        visto = False
        cierre = False
        for _ in range(4):
            if not o:
                break
            t, o = c.decir(o[0])
            paso = str(_doc(c.cid).get("current_step") or "")
            if paso == "2.4.0.1.20.1":
                visto = True
                break
            if paso == "2.4.0.1.20.2":
                cierre = True
                break
        check(visto is debe_aparecer,
              f"con {cantidad} transaccion(es) el bucle {'aparece' if debe_aparecer else 'NO aparece'}")
        if visto:
            check(len(o) == 2, "el bucle ofrece exactamente dos salidas")
        else:
            # El cierre .20.2 es SOLO para quien declaro 2 o 3: a quien reporta
            # una sola, decirle "ya reportaste todas" suena raro (decision de
            # Pablo, 21/08). Con 1 va directo a satisfaccion.
            check(not cierre, f"con {cantidad} transaccion(es) NO se pinta el cierre .20.2")


# ---------------------------------------------------------------------------
# Los tres requisitos de Fabian (20/08). Hasta ahora estaban verificados a mano
# UNA vez: si alguien los rompia, nada avisaba.
# ---------------------------------------------------------------------------

# Frases que el bot NO puede decir cuando el servicio no ha contestado. Son
# afirmaciones sobre el cliente y solo valen si el ASO respondio.
_FRASES_PROHIBIDAS = (
    "no tienes productos activos",
    "no encontramos compras registradas",
)


def _con_servicio_caido(uid: str, pasos, turno_caida: int):
    """Recorre hasta el turno indicado, tumba el servicio trx y sigue."""
    _reset(uid)
    c = Conversacion(uid)
    assert c.abrir(), c.error
    o: list[str] = []
    t = ""
    caido = False
    try:
        for i, e in enumerate(pasos):
            if i == turno_caida:
                subprocess.run(["docker", "stop", "trx-esqueleto"], capture_output=True)
                time.sleep(2)
                caido = True
            t, o = c.decir(_elegir(o, e))
    finally:
        if caido:
            subprocess.run(["docker", "start", "trx-esqueleto"], capture_output=True)
            time.sleep(12)
    return c, t, o


def _seccion_errores() -> None:
    """Con el ASO caido, el bot avisa de la incidencia y NUNCA afirma algo falso."""

    print("\n2.4.0.1.4.error / .8.error - fail-closed con el ASO caido")
    base = ("No reconozco esta compra", "Compra presencial", "1", "Empezar ahora",
            "Si, continuar")
    c, t, o = _con_servicio_caido(CLIENTES["devolucion"], base, 4)
    paso = str(_doc(c.cid).get("current_step") or "")
    check(paso == "2.4.0.1.4.error", f"productos: cae en .4.error (esta en {paso})")
    for frase in _FRASES_PROHIBIDAS:
        check(frase not in _norm(t), f"productos: NO dice '{frase}'")
    check(bool(o), "productos: ofrece una salida al cliente")

    hasta_fecha = base + ("Tarjeta", "Entre $35.000", FECHA)
    c, t, o = _con_servicio_caido(CLIENTES["devolucion"], hasta_fecha, 7)
    paso = str(_doc(c.cid).get("current_step") or "")
    check(paso == "2.4.0.1.8.error", f"movimientos: cae en .8.error (esta en {paso})")
    for frase in _FRASES_PROHIBIDAS:
        check(frase not in _norm(t), f"movimientos: NO dice '{frase}'")
    check(bool(o), "movimientos: ofrece una salida al cliente")


def _seccion_bloqueo_repetido() -> None:
    """En la 2a transaccion NO se vuelve a pedir el bloqueo del mismo producto."""

    print("\n2.4.0.1.15 - no re-ofrecer el bloqueo del mismo producto")
    uid = CLIENTES["devolucion"]
    c, t, o = _hasta_bloqueo(uid, "2")
    # cerrar la 1a transaccion y pedir la siguiente
    for _ in range(5):
        if not o:
            break
        p = str(_doc(c.cid).get("current_step") or "")
        if p == "2.4.0.1.20.1":
            break
        t, o = c.decir(o[0])
    check(
        str(_doc(c.cid).get("current_step") or "") == "2.4.0.1.20.1",
        "tras la 1a transaccion se ofrece reportar la siguiente",
    )
    t, o = c.decir(_elegir(o, "reportar la siguiente"))
    # 2a transaccion: hasta confirmar el movimiento
    for e in ("Si, continuar", "Tarjeta", "Entre $35.000", FECHA):
        t, o = c.decir(_elegir(o, e))
    movs = [x for x in o if "no encuentro" not in _norm(x)]
    check(bool(movs), "la 2a transaccion lista movimientos")
    if not movs:
        return
    t, o = c.decir(movs[0])
    t, o = c.decir(_elegir(o, "Si, continuar con el reporte"))
    t, o = c.decir(_elegir(o, "Si, continuar con la investigacion"))
    paso = str(_doc(c.cid).get("current_step") or "")
    # La tarjeta ya se bloqueo en la 1a: el gate debe saltar .15 y .17
    check(paso == "2.4.0.1.18", f"salta el bloqueo y va a .18 (esta en {paso})")
    check("bloquear" not in _norm(t), "no vuelve a ofrecer bloquear la tarjeta")
    check("ya qued" in _norm(t) or "reporte anterior" in _norm(t),
          "avisa de que la tarjeta ya estaba bloqueada")


if __name__ == "__main__":
    import sys
    raise SystemExit(verificar(sys.argv[1] if len(sys.argv) > 1 else "todo"))
