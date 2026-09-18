"""Ejercita cada casuistica de Doble Cobro contra el agente vivo y compara lo
que responde con lo esperado.

    python scripts/casuisticas_doble_cobro.py          # todas
    python scripts/casuisticas_doble_cobro.py B        # solo las del grupo B

Necesita levantados el agente (:8000), doble cobro (:8006) y el simulador ASO
(:8050). Es la version ejecutable de docs/PRUEBAS_DOBLE_COBRO.md, que explica
cada caso; aqui solo esta la comprobacion.

Los casos de vigencia afirman ademas el ``outcome`` que devuelve el :8006,
porque desde el chat NO se distingue "fuera de los 6 meses" de "vencida la
franquicia": 3.4.0.3.pqr usa el mismo texto para las dos.

Las FECHAS de abajo las genera gen_doble_cobro_fixtures.py del simulador y
caducan solas. Si empiezan a fallar casos de vigencia, regenera los fixtures y
copia aqui las fechas que imprime el script.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            b = r.read().decode()
            return r.status, (json.loads(b) if b else None)
    except urllib.error.HTTPError as e:
        b = e.read().decode()
        try:
            return e.code, json.loads(b)
        except Exception:
            return e.code, b[:200]


DOBLE_COBRO = "http://127.0.0.1:8006"


def outcome_vigencia(fecha, product_type, card_brand=""):
    """Regla que corta en 3.4.0.3, preguntandosela al servicio.

    Hace falta porque desde el chat NO se distinguen: "fuera de los 6 meses" y
    "vencida la franquicia" comparten el mismo texto de 3.4.0.3.pqr, asi que
    afirmar sobre el mensaje no prueba cual de las dos reglas disparo.
    """

    req = urllib.request.Request(
        DOBLE_COBRO + "/v0/doble-cobro/validar-vigencia",
        data=json.dumps({
            "transaction_date": fecha,
            "product_type": product_type,
            "card_brand": card_brand,
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return (json.loads(r.read().decode()).get("data") or {}).get("outcome")


def envelope(d):
    m = (d or {}).get("message") or {}
    c = m.get("content") or {}
    return m.get("message_id"), (c.get("label") or ""), (c.get("options") or [])


def turno(cid, content):
    st, d = call("POST", "/chat", {"conversation_id": cid, "content": content})
    _, label, _ = envelope(d)
    if st == 204 or "revisando tu informaci" in label:
        for _ in range(40):
            time.sleep(1.5)
            ps, _pd = call("POST", "/polling", {"conversation_id": cid})
            if ps in (200, 303):
                _gs, gd = call("GET", f"/polling/{cid}")
                d = gd
                break
    return envelope(d)


def correr(caso):
    user = caso["user"]
    call("POST", "/end", {"conversation_id": f"{user}_20260908"})
    st, d = call("POST", "/start", {"user_id": user})
    if not isinstance(d, dict) or not d.get("conversation_id"):
        return {"ok": False, "detalle": f"/start fallo: {st} {d}"}
    cid = d["conversation_id"]

    label, options, ids = "", [], []
    for paso in caso["pasos"]:
        mid, label, options = turno(cid, paso)
        ids.append(mid)

    keys = [o["key"] for o in options]
    labels = [o["label"] for o in options]

    fallos = []
    esperado = caso["espera"]

    if "texto" in esperado and esperado["texto"].lower() not in label.lower():
        fallos.append(f"texto: no aparece {esperado['texto']!r} en {label[:110]!r}")

    if "keys" in esperado and keys != esperado["keys"]:
        fallos.append(f"keys: {keys} != {esperado['keys']}")

    if "n_transacciones" in esperado:
        n = len([k for k in keys if k.startswith("transaccion_")])
        if n != esperado["n_transacciones"]:
            fallos.append(f"transacciones: {n} != {esperado['n_transacciones']}")

    if "sin_opciones" in esperado and bool(keys) == esperado["sin_opciones"]:
        fallos.append(f"opciones: esperaba {'ninguna' if esperado['sin_opciones'] else 'algunas'}, hay {keys}")

    if "regex" in esperado and not re.search(esperado["regex"], label, re.I):
        fallos.append(f"regex {esperado['regex']!r} no casa con {label[:110]!r}")

    if "n_opciones" in esperado and len(keys) != esperado["n_opciones"]:
        fallos.append(f"opciones: {len(keys)} != {esperado['n_opciones']} ({keys})")

    if "outcome" in esperado:
        real = outcome_vigencia(*esperado["outcome"][:-1])
        if real != esperado["outcome"][-1]:
            fallos.append(f"outcome: {real} != {esperado['outcome'][-1]}")

    if "una_tarjeta" in esperado:
        selectores = [i for i, k in zip(ids, caso["pasos"]) if str(k).startswith("transaccion_")]
        if len(set(selectores)) > 1:
            fallos.append(f"la tarjeta se duplico: {len(set(selectores))} ids distintos")

    return {
        "ok": not fallos,
        "detalle": "; ".join(fallos),
        "label": label[:150].replace("\n", " | "),
        "labels": labels,
    }


# --- fechas que genera gen_doble_cobro_fixtures.py para hoy (2026-09-08) -----
RECIENTE = "03/09/2026"
FRONTERA = "28/08/2026"
FELIZ = "21/08/2026"
LIMITE = "10/08/2026"
PAGINACION = "31/07/2026"
FRANQ_MASTER = "10/04/2026"
VENCIDA = "09/01/2026"
# Dia habil y dentro de plazo, pero SIN ningun movimiento en el fixture.
SIN_MOVIMIENTOS = "26/08/2026"

INTENT = "me cobraron dos veces la misma compra"
C = "13083558"

CASOS = [
    # --- 3.4.0: familia de producto ---------------------------------------
    {"id": "A1-tarjeta-credito", "user": C,
     "pasos": [INTENT, "CREDIT_CARD"],
     "espera": {"texto": "formulario"},
     "nota": "Tarjeta de credito no entra al flujo: va a PQR."},

    {"id": "A2-sin-productos", "user": "13083560",
     "pasos": [INTENT, "SAVING"],
     "espera": {"texto": "No pude consultar tus productos"},
     "nota": "Cliente sin productos -> 3.4.0.1.pqr."},

    {"id": "A3-selector-productos", "user": C,
     "pasos": [INTENT, "SAVING"],
     "espera": {"keys": ["producto_1", "producto_2", "producto_3"]},
     "nota": "Tres productos activos."},

    # --- 3.4.0.3: vigencia -------------------------------------------------
    {"id": "B1-conciliacion", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", RECIENTE],
     "espera": {"regex": r"conciliaci.n de 7 d.as h.biles", "sin_opciones": True},
     "nota": "3 habiles: aun en conciliacion."},

    {"id": "B2-frontera-7-habiles", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", FRONTERA],
     "espera": {"texto": "monto"},
     "nota": "7 habiles justos: ya se puede reclamar."},

    {"id": "B3-fuera-de-6-meses", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", VENCIDA],
     "espera": {"texto": "supera el plazo",
                "outcome": (VENCIDA, "ACCOUNT", "", "report_window_expired")},
     "nota": "Fuera de los 6 meses (NO franquicia) -> PQR."},

    {"id": "B4-franquicia-master", "user": "13083559",
     "pasos": [INTENT, "SAVING", "producto_1", FRANQ_MASTER],
     "espera": {"texto": "supera el plazo",
                "outcome": (FRANQ_MASTER, "CARD", "MASTER", "franchise_expired")},
     "nota": "MASTER: 120 dias. Con VISA esta fecha seguiria."},

    # --- 3.4.0.6: seleccion ------------------------------------------------
    {"id": "C1-grupo-de-3", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", FELIZ, "145000"],
     "espera": {"n_transacciones": 2, "texto": "Selecciona las duplicadas"},
     "nota": "Grupo de 3 cargos -> 2 reportables."},

    {"id": "C2-grupo-de-2", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", FELIZ, "88000"],
     "espera": {"n_transacciones": 1},
     "nota": "Grupo de 2 -> 1 reportable."},

    {"id": "C3-tolerancia-monto", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", FELIZ, "146500"],
     "espera": {"n_transacciones": 2},
     "nota": "Tolerancia +-2000 al BUSCAR: cae en el grupo de 145000."},

    {"id": "C4-cargo-unico", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", FELIZ, "210000"],
     "espera": {"texto": "no podemos identificar"},
     "nota": "Sin pareja -> 3.4.0.6.pqr."},

    {"id": "C5-trampa-monto", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", LIMITE, "76000"],
     "espera": {"texto": "no podemos identificar"},
     "nota": "76000 y 76500: al AGRUPAR el monto debe ser identico."},

    {"id": "C6-trampa-comercio", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", LIMITE, "15000"],
     "espera": {"texto": "no podemos identificar"},
     "nota": "Mismo monto y minuto, comercios distintos."},

    {"id": "C7-horas-distintas", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", LIMITE, "47000"],
     "espera": {"n_transacciones": 1},
     "nota": "3 horas de diferencia: agrupan igual, la hora no interviene."},

    {"id": "C8-triple", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", LIMITE, "24500"],
     "espera": {"n_transacciones": 2},
     "nota": "Triple cobro -> 2 reportables."},

    # --- paginacion --------------------------------------------------------
    {"id": "D1-primera-pagina", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", PAGINACION, "34000"],
     "espera": {"n_transacciones": 6},
     "nota": "8 sobrantes: la primera pagina muestra 6 + 'Ver mas'."},

    {"id": "D2-segunda-pagina", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", PAGINACION, "34000", "mas_movimientos"],
     "espera": {"n_transacciones": 2},
     "nota": "Segunda pagina: los 2 restantes, sin 'Ver mas'."},

    # --- seleccion multiple y tarjeta unica --------------------------------
    {"id": "E1-contador", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", FELIZ, "145000",
               "transaccion_1", "transaccion_2"],
     "espera": {"texto": "Llevas 2 transacci", "una_tarjeta": True},
     "nota": "Dos casillas marcadas, una sola tarjeta."},

    {"id": "E2-desmarcar", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", FELIZ, "145000",
               "transaccion_1", "transaccion_1"],
     "espera": {"texto": "Llevas 0 transacci"},
     "nota": "El clic alterna."},

    {"id": "E3-no-encuentro", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", FELIZ, "145000", "no_encuentro"],
     "espera": {"texto": "no podemos identificar"},
     "nota": "Salida manual -> PQR."},

    # --- registro ----------------------------------------------------------
    {"id": "F1-registro", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", FELIZ, "145000",
               "transaccion_1", "transaccion_2", "reportar_seleccionados"],
     "espera": {"texto": "Hemos registrado tu reporte", "sin_opciones": True},
     "nota": "Camino feliz completo."},

    {"id": "F2-recurrencia-no-bloquea", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", FELIZ, "145000",
               "transaccion_1", "reportar_seleccionados"],
     "espera": {"texto": "Hemos registrado tu reporte"},
     "nota": "Repetir el mismo reporte: reemplaza, no bloquea."},

    # --- otros productos ---------------------------------------------------
    {"id": "G1-cuenta-meta", "user": C,
     "pasos": [INTENT, "SAVING", "producto_2", FELIZ, "99000"],
     "espera": {"n_transacciones": 1},
     "nota": "CUENTA META tiene su propio juego de datos."},

    {"id": "G2-visa-debito", "user": C,
     "pasos": [INTENT, "SAVING", "producto_3", FELIZ, "189000"],
     "espera": {"n_transacciones": 1},
     "nota": "Tarjeta debito VISA."},

    {"id": "D3-seleccion-cruza-pagina", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", PAGINACION, "34000",
               "transaccion_1", "mas_movimientos", "transaccion_7"],
     "espera": {"texto": "Llevas 2 transacci"},
     "nota": "La seleccion sobrevive al cambio de pagina."},

    {"id": "B5-master-camino-feliz", "user": "13083559",
     "pasos": [INTENT, "SAVING", "producto_1", FELIZ, "75000"],
     "espera": {"n_transacciones": 1},
     "nota": "Contraste de B4: la MASTER dentro de plazo si llega al selector."},

    {"id": "F3-reportar-sin-seleccion", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", FELIZ, "145000",
               "reportar_seleccionados"],
     "espera": {"texto": "Selecciona al menos un cobro"},
     "nota": "Por API: vuelve al selector con aviso (el front lo deshabilita)."},

    {"id": "H1-visa-frontera", "user": C,
     "pasos": [INTENT, "SAVING", "producto_3", FRONTERA],
     "espera": {"texto": "monto"},
     "nota": "Visa Debito: la frontera de 7 habiles es la misma que en cuentas."},

    {"id": "H2-visa-franquicia", "user": C,
     "pasos": [INTENT, "SAVING", "producto_3", "11/03/2026"],
     "espera": {"texto": "supera el plazo",
                "outcome": ("11/03/2026", "CARD", "VISA", "franchise_expired")},
     "nota": "Visa Debito: supera los 180 dias de VISA."},

    {"id": "H3-cargo-unico-limite", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", LIMITE, "57000"],
     "espera": {"texto": "no podemos identificar"},
     "nota": "LIBRERIA NACIONAL: cargo unico el dia de casos limite."},

    {"id": "B6-misma-fecha-visa-pasa", "user": C,
     "pasos": [INTENT, "SAVING", "producto_3", FRANQ_MASTER],
     "espera": {"texto": "monto",
                "outcome": (FRANQ_MASTER, "CARD", "VISA", "ok")},
     "nota": "MISMA fecha que B4, pero VISA (180 dias): avanza a pedir el monto."},

    {"id": "B7-misma-fecha-cuenta-pasa", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", FRANQ_MASTER],
     "espera": {"texto": "monto",
                "outcome": (FRANQ_MASTER, "ACCOUNT", "", "ok")},
     "nota": "MISMA fecha, cuenta de ahorro: sin marca, no aplica franquicia."},

    # --- I. Cliente sin cobros duplicados ---------------------------------
    {"id": "I1-dia-sin-movimientos", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", SIN_MOVIMIENTOS, "50000"],
     "espera": {"texto": "no podemos identificar", "keys": ["pqr"]},
     "nota": "Dia habil y en plazo, pero SIN ningun movimiento."},

    {"id": "I2-monto-ilegible", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", FELIZ, "como cien mil"],
     "espera": {"texto": "no podemos identificar"},
     "nota": "Monto no parseable: no encuentra grupos, no revienta."},

    {"id": "I3-monto-cero", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", FELIZ, "0"],
     "espera": {"texto": "no podemos identificar"},
     "nota": "Monto 0."},

    # --- J. Salidas a PQR y satisfaccion ----------------------------------
    {"id": "J1-cuenta-corriente", "user": C,
     "pasos": [INTENT, "CHECKING"],
     "espera": {"keys": ["producto_1"]},
     "nota": "Corriente: solo la debito, que cuelga de ambas familias."},

    {"id": "J2-pqr-grupos-a-satisfaccion", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", FELIZ, "210000", "pqr"],
     "espera": {"n_opciones": 2, "regex": r"\?"},
     "nota": "El boton 'Formulario PQR' de 3.4.0.6.pqr cierra en satisfaccion."},

    {"id": "J3-pqr-credito-a-satisfaccion", "user": C,
     "pasos": [INTENT, "CREDIT_CARD", "pqr"],
     "espera": {"n_opciones": 2, "regex": r"\?"},
     "nota": "Lo mismo desde 3.4.0.pqr_tarjeta_credito."},

    {"id": "J4-fecha-ilegible", "user": C,
     "pasos": [INTENT, "SAVING", "producto_1", "no me acuerdo"],
     "espera": {"keys": ["pqr"]},
     "nota": "Fecha ilegible: fail-closed a PQR (el front usa calendario)."},
]


def main():
    filtro = sys.argv[1] if len(sys.argv) > 1 else ""
    casos = [c for c in CASOS if filtro.lower() in c["id"].lower()]
    fallidos = []

    for caso in casos:
        r = correr(caso)
        marca = "OK  " if r["ok"] else "FALLA"
        print(f"[{marca}] {caso['id']:26} {caso['nota']}")
        if not r["ok"]:
            print(f"         -> {r['detalle']}")
            print(f"         label: {r['label']}")
            fallidos.append(caso["id"])
        else:
            print(f"         {r['label']}")
            for lb in r["labels"][:9]:
                print(f"           - {lb[:74]}")
        print()

    print(f"== {len(casos) - len(fallidos)}/{len(casos)} correctos")
    if fallidos:
        print("   fallan:", ", ".join(fallidos))
    return 1 if fallidos else 0


sys.exit(main())
