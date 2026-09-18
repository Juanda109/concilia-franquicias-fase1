"""F2 - Recorre las 26 transiciones del tramo de Luis y captura lo REAL.

El tramo de Luis (2.4.0.1.12 en adelante) tiene 20 pasos y 26 aristas. Siete de
esos pasos NO tienen boton que lleve a ellos: se alcanzan solo por redireccion
desde codigo (los desenlaces y los caminos de error). Un recorrido "feliz" toca
menos de la mitad, y por eso 25 de las 26 filas del Excel seguian en blanco.

Cada recorrido guarda, turno a turno: el paso, el texto LITERAL del bot y los
botones. Con eso se rellenan las columnas F/G del Excel y se contrasta contra el
tablero sin depender de la memoria de nadie.

Uso:  python3 capturar_tramo_luis.py            (stack local; ver BITACORA_F0)
      python3 capturar_tramo_luis.py P3         (solo un recorrido)

Salida: captura_tramo_luis.json
"""

from __future__ import annotations

import json
import re
import ssl
import subprocess
import sys
import unicodedata
import urllib.request

from runner import Conversacion

OS_URL = "https://localhost:9200"
BASIC = "Basic YWRtaW46YWRtaW4="          # admin/admin, OpenSearch local de pruebas


def _paso_real(conversation_id: str) -> str:
    """El current_step que ha quedado en OpenSearch tras el turno.

    Se lee de la fuente y no se deduce del texto: muchos pasos de este tramo
    generan su mensaje desde Python (mostrar_bloqueo_*, mostrar_trx_*), asi que
    el 'question' del YAML no coincide con lo que ve el cliente y emparejar por
    texto da una cobertura falsamente baja.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        f"{OS_URL}/conversations-reference/_doc/{conversation_id}",
        headers={"Authorization": BASIC},
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            return str(json.loads(r.read())["_source"].get("current_step") or "")
    except Exception:
        return ""

# Hasta la frontera .11 el camino es el de mi tramo; a partir de ahi, el suyo.
def _hasta_confirmacion(cantidad: str = "1") -> list[str]:
    """Camino hasta la frontera .11. La CANTIDAD importa: con "1" el flujo
    salta 2.4.0.1.20.1 y va directo a satisfaccion, porque no hay siguiente
    transaccion que reportar. Ese paso solo existe si se pidieron 2 o 3."""
    return ["No reconozco esta compra", "Compra presencial", cantidad,
            "Empezar ahora", "Si, continuar", "Tarjeta", "Entre $35.000",
            "06/08/2026", "@movimiento"]

# (id, cliente, pasos tras la confirmacion, que se pretende cubrir)
RECORRIDOS = [
    ("P1", "1013634970", ["Si, continuar con el reporte", "Si, continuar con la investigacion",
                          "Si, bloquear definitivamente", "Si, bloquear y continuar",
                          "Continuar", "Continuar", "Continuar", "No, finalizar"],
     "bloqueo definitivo -> devolucion -> no reportar otra"),
    ("P2", "1013634961", ["Si, continuar con el reporte", "Si, continuar con la investigacion",
                          "Si, bloquear definitivamente", "Si, bloquear y continuar",
                          "Continuar", "Continuar", "Continuar", "Si, reportar la siguiente"],
     "bucle: reportar la 2a transaccion (vuelve a 2.4.0.1.3)", "2"),
    ("P2b", "1013634970", ["Si, continuar con el reporte", "Si, continuar con la investigacion",
                           "Si, bloquear definitivamente", "Si, bloquear y continuar",
                           "Continuar", "Continuar", "Continuar", "No, finalizar"],
     "2.4.0.1.20.1 -> no reportar la siguiente", "2"),
    ("P3", "1013634972", ["Si, continuar con el reporte", "Si, continuar con la investigacion",
                          "No, bloquear temporalmente", "Si, apagar temporalmente",
                          "Continuar", "Terminar"],
     "bloqueo temporal completo"),
    ("P4", "1013634962", ["Si, continuar con el reporte", "No, finalizar la conversacion"],
     "salida en .13 (no inicia investigacion)"),
    ("P5", "1013634963", ["Si, continuar con el reporte", "Si, continuar con la investigacion",
                          "No, bloquear temporalmente", "No, finalizar conversacion"],
     "salida en .16 (no apaga la tarjeta)"),
    ("P6", "1013634960", ["Si, continuar con el reporte", "Si, continuar con la investigacion",
                          "Si, bloquear definitivamente", "No, finalizar conversacion"],
     "salida en .17 (no bloquea definitivamente)"),
    ("P11", "1013634964", ["Si, continuar con el reporte", "Terminar"],
     "gate validar_pendiente_trx -> 2.4.0.1.12.exit -> Terminar"),
    ("P7", "1013634971", ["Si, continuar con el reporte", "Si, continuar con la investigacion",
                          "Si, bloquear definitivamente", "Si, bloquear y continuar",
                          "Continuar", "Continuar", "Continuar", "Finalizar"],
     "desenlace PRESENCIAL (.19.1)"),
    ("P8", "1013634972", ["Si, continuar con el reporte", "Si, continuar con la investigacion",
                          "Si, bloquear definitivamente", "Si, bloquear y continuar",
                          "Continuar", "Continuar", "Continuar",
                          "Ver paso a paso", "Finalizar"],
     "desenlace REVERSADO + guia paso a paso (.19.2 / .19.2.guia)"),
    ("P9", "1013634960", ["Si, continuar con el reporte", "Si, continuar con la investigacion",
                          "Si, bloquear definitivamente", "Si, bloquear y continuar",
                          "Continuar", "Continuar", "Continuar", "Formulario PQR"],
     "desenlace PQR (.19.pqr)"),
    ("P10", "1013634972", ["Si, continuar con el reporte", "Si, continuar con la investigacion",
                           "Si, bloquear definitivamente", "Si, bloquear y continuar",
                           "Continuar", "Continuar", "Continuar", "Finalizar"],
     "desenlace REVERSADO, salida directa sin guia"),
]


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def _reset(uid: str) -> None:
    subprocess.run(["./reset_cliente.sh", uid], capture_output=True, check=False)


def _elegir(opciones: list[str], texto: str) -> tuple[str, bool]:
    """Devuelve (etiqueta a enviar, si caso con un boton real)."""
    if texto == "@movimiento":
        movs = [o for o in opciones if "no encuentro" not in _norm(o)]
        return (movs[0], True) if movs else (texto, False)
    hit = next((o for o in opciones if _norm(texto) in _norm(o)), None)
    if hit is None and _norm(texto).startswith("tarjeta"):
        # solo-FO: la etiqueta del selector es el nombre real del producto
        # ("VISA ORO LM •0060"); se elige la primera opcion con mascara.
        hit = next((o for o in opciones if "•" in o), None)
    return (hit, True) if hit else (texto, False)


def recorrer(rid: str, uid: str, pasos_luis: list[str], proposito: str,
             cantidad: str = "1") -> dict:
    _reset(uid)
    c = Conversacion(uid)
    if not c.abrir():
        return {"id": rid, "uid": uid, "proposito": proposito, "error": c.error, "turnos": []}
    turnos: list[dict] = []
    o: list[str] = []
    for paso in _hasta_confirmacion(cantidad) + pasos_luis:
        etiqueta, caso = _elegir(o, paso)
        t, o = c.decir(etiqueta)
        turnos.append({
            "pedido": paso, "enviado": etiqueta, "caso_boton": caso,
            "paso": _paso_real(c.cid),
            "texto": " ".join((t or "").split()), "opciones": list(o),
        })
        if c.error:
            turnos[-1]["error"] = c.error
            break
    _reset(uid)
    return {"id": rid, "uid": uid, "proposito": proposito, "turnos": turnos}


if __name__ == "__main__":
    filtro = sys.argv[1] if len(sys.argv) > 1 else None
    salida = []
    for entrada in RECORRIDOS:
        rid, uid, pasos, prop = entrada[:4]
        cantidad = entrada[4] if len(entrada) > 4 else "1"
        if filtro and rid not in {x.strip() for x in filtro.split(",")}:
            continue
        r = recorrer(rid, uid, pasos, prop, cantidad)
        salida.append(r)
        sin_boton = [t["pedido"] for t in r["turnos"] if not t.get("caso_boton")]
        err = next((t.get("error") for t in r["turnos"] if t.get("error")), None)
        print(f"{rid:<4} {uid:<12} turnos={len(r['turnos']):<3} "
              f"sin_boton={len(sin_boton)}{' ERROR: ' + str(err) if err else ''}")
        if sin_boton:
            print(f"     no casaron: {sin_boton}")
    with open("captura_tramo_luis.json", "w") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)
    print("\n-> captura_tramo_luis.json")
