"""F3 — verifica el contrato de la frontera (2.4.0.1.11 -> 2.4.0.1.12).

Recorre el camino feliz (cliente C) hasta entregar en la zona de Luis y valida
que TODAS las claves del contrato esten presentes y bien formadas en
captured_data / flow_answers. Es el contrato hecho ejecutable: si Luis y yo lo
corremos cada uno por su lado, no podemos divergir sin que falle.

Uso:  python3 verificar_contrato.py   (stack local levantado; ver BITACORA_F0)
"""

from __future__ import annotations

import json
import ssl
import subprocess
import urllib.request

from runner import Conversacion, _norm

CLIENTE = "1013634960"          # C: 3 movs, eci=5, eCard=true -> devolucion
OS_URL = "https://localhost:9200"

CAMINO = [
    "No reconozco esta compra",
    "Compra presencial o por internet",   # gate .1 valida y salta a cantidad
    "1",
    "Empezar ahora",
    "Si, continuar",                       # -> gate .4 (productos) -> selector
    "Tarjeta de Credito",   # el boton es "Tarjeta de Credito •0060" (mascara del tablero)
    "Entre $35.000 y $500.000",
    "06/08/2026",                          # -> gate .8 -> listado
    "COMPRA FALABELLA CALLE 80",           # -> gate .10 -> confirmacion
    "Si, continuar con el reporte",        # -> gate .12 -> FRONTERA (.13)
]


def _leer_conversacion(conversation_id: str) -> dict:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        f"{OS_URL}/conversations-reference/_doc/{conversation_id}",
        headers={"Authorization": "Basic YWRtaW46YWRtaW4="},  # admin/admin local
    )
    with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
        return json.loads(r.read())["_source"]


def verificar() -> int:
    # Resetear ANTES de recorrer: hay una conversacion por cliente y dia, y si
    # queda una de una pasada anterior el /start RETOMA donde se quedo. El
    # CAMINO fijo se desincroniza en el primer paso y el fallo parece del
    # flujo cuando es del entorno.
    subprocess.run(["./reset_cliente.sh", CLIENTE], capture_output=True, check=False)
    c = Conversacion(CLIENTE)
    assert c.abrir(), c.error
    t, o = "", []
    for paso in CAMINO:
        # elegir por contenido: las etiquetas dinamicas llevan importe y fecha
        elegida = next((x for x in o if _norm(paso) in _norm(x)), None)
        if elegida is None and _norm(paso).startswith("tarjeta"):
            # solo-FO: la etiqueta del selector es el nombre real del producto.
            elegida = next((x for x in o if "•" in x), None)
        if elegida is None:
            elegida = paso
        t, o = c.decir(elegida)
        if c.error:
            print(f"NO LLEGO A LA FRONTERA: {c.error} (tras {paso!r})")
            return 1
    if "investigacion" not in _norm(t):
        print(f"NO ES LA FRONTERA: {' '.join((t or '').split())[:120]}")
        return 1

    doc = _leer_conversacion(c.cid)
    fa, cd = doc.get("flow_answers", {}), doc.get("captured_data", {})
    fallos: list[str] = []

    def check(cond: bool, etiqueta: str) -> None:
        print(f"  [{'OK ' if cond else 'FALLA'}] {etiqueta}")
        if not cond:
            fallos.append(etiqueta)

    print(f"\nContrato v1 en {c.cid} (current_step={doc.get('current_step')}):\n")

    # --- claves de flow_answers (las fija save_as del YAML) ---
    for k in ("trx_cantidad", "producto_trx_no_reconocida", "trx_fecha",
              "trx_movimiento_seleccionado", "trx_confirmacion_movimiento"):
        check(bool(fa.get(k)), f"flow_answers.{k} presente")
    check(fa.get("trx_confirmacion_movimiento") == "si_reportar",
          "la frontera solo se cruza con confirmacion afirmativa")

    # --- claves de captured_data que Luis consume ---
    check(bool(cd.get("trx_card_id")), "trx_card_id (lo leen los bloqueos)")
    check(cd.get("trx_vigencia") == "vigente", "trx_vigencia == vigente")
    check(bool(cd.get("trx_index")), "trx_index (bucle multi-transaccion)")

    cla = json.loads(cd.get("trx_clasificacion") or "{}")
    for k in ("pendiente_tdc", "eci", "ecard", "reversado", "response", "resultado"):
        check(k in cla, f"trx_clasificacion.{k}")

    movs = json.loads(cd.get("trx_movimientos_result") or "{}")
    check(bool(movs.get("movimientos")), "trx_movimientos_result.movimientos")
    sf = json.loads(cd.get("trx_salesforce_result") or "{}")
    check("has_recurrence" in sf, "trx_salesforce_result.has_recurrence")

    det = json.loads(cd.get("trx_detalle_result") or "{}")
    for k in ("id", "responseOperati", "eci", "eCard", "dateOper"):
        check(k in det, f"trx_detalle_result.{k}")

    # --- el producto autoritativo es products_result, NO products_map ---
    idx = int(str(fa.get("producto_trx_no_reconocida", "producto_1")).rsplit("_", 1)[-1]) - 1
    prods = (json.loads(cd.get("trx_products_result") or "{}").get("data") or {}).get("products") or []
    prod = prods[idx] if idx < len(prods) else {}
    check(prod.get("origin_flag") in ("TDC", "Pasivo", "PASIVO"),
          "products_result[idx].origin_flag (rombo '¿Compra con TC?' de Luis)")
    check(bool(prod.get("last_four")), "products_result[idx].last_four")
    check(bool(prod.get("card_brand")), "products_result[idx].card_brand")

    pm = (json.loads(cd.get("trx_products_map") or "[]") or [{}])[idx if idx < len(prods) else 0]
    if not pm.get("origin_flag"):
        print("  [AVISO] trx_products_map NO lleva origin_flag/last_four: es la copia "
              "de presentacion. Consumir products_result, no el map.")

    # La regla de los 7 dias del tablero NO necesita fecha de cruce. Fabian lo
    # zanjo el 20/08: el estado "pendiente" ya encierra esa ventana -- una
    # compra deja de estar pendiente en cuanto se cruza, y el cruce ocurre
    # dentro de los 7 dias. Lo que el tablero dibuja como "o ya supero los 7
    # dias" lo resuelve el ASO aguas arriba, no el bot. Aqui se comprueba lo
    # que el flujo SI necesita: el estado de la operacion.
    check(
        "responseOperati" in det or "process" in det,
        "el detalle trae el estado de la operacion (insumo de pendiente_tdc)",
    )

    print(f"\n{'CONTRATO OK' if not fallos else f'{len(fallos)} INCUMPLIMIENTOS'}")
    return 0 if not fallos else 1


if __name__ == "__main__":
    raise SystemExit(verificar())
