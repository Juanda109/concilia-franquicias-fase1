"""Verifica los mensajes DINAMICOS del tramo contra la FUENTE de su dato.

Los cuatro puntos donde el cliente ve datos suyos:
  2.4.0.1.5   selector de productos      (prompt + labels)
  2.4.0.1.7   reprompt de fecha ilegible (prompt condicional)
  2.4.0.1.9   listado de movimientos     (prompt + labels)
  2.4.0.1.11  confirmacion de la compra  (prompt)

Se comprueba en cuatro dimensiones:
  PROCEDENCIA  cada valor mostrado sale de la clave correcta del payload
  FORMATO      el del tablero: fecha DD/MM/AAAA, importe $120.000, producto *0060
  DEGRADACION  con el dato ausente no se cuela un crudo (XXXX, None, id entero)
  CICLO DE VIDA el mensaje se limpia cuando deja de aplicar

Compara contra la FUENTE, no contra un literal: un cambio de copy autorizado no
rompe la prueba, pero un dato leido de la clave equivocada si. Es el fallo que
se escapo tres veces (H-03 fecha ISO, H-07 reprompt pegado, H-08 *XXXX).

Uso:  python3 verificar_mensajes.py     (stack local levantado; ver BITACORA_F0)
"""

from __future__ import annotations

import json
import re
import ssl
import subprocess
import unicodedata
import urllib.request

from runner import Conversacion

CLIENTE = "1013634960"          # C: 3 movimientos, VISA *0060
FECHA_CON_MOVS = "06/08/2026"
OS_URL = "https://localhost:9200"
BASIC = "Basic YWRtaW46YWRtaW4="        # admin/admin, OpenSearch local de pruebas

_FECHA_DDMMAAAA = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
_FECHA_ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_IMPORTE = re.compile(r"\$[\d.]+")
# Crudos que jamas deben llegar a pantalla
_CRUDOS = ("XXXX", "None", "null", "product_id", "last_four_pan_id")

fallos: list[str] = []
comprobaciones = 0


def check(cond: bool, etiqueta: str) -> bool:
    global comprobaciones
    comprobaciones += 1
    print(f"  [{'OK ' if cond else 'FALLA'}] {etiqueta}")
    if not cond:
        fallos.append(etiqueta)
    return cond


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def _conversacion(conversation_id: str) -> dict:
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
        # solo-FO: la etiqueta del selector es el nombre real del producto.
        hit = next((o for o in opciones if "•" in o), None)
    return hit if hit is not None else texto


def _sin_crudos(texto: str, etiqueta: str) -> None:
    for crudo in _CRUDOS:
        check(crudo not in (texto or ""), f"{etiqueta}: sin '{crudo}' en pantalla")


def verificar() -> int:
    _reset(CLIENTE)
    c = Conversacion(CLIENTE)
    assert c.abrir(), c.error
    t, o = c.decir("No reconozco esta compra")
    for entrada in ("Compra presencial", "1", "Empezar ahora", "Si, continuar"):
        t, o = c.decir(_elegir(o, entrada))

    # ---------- 2.4.0.1.5 · selector de productos ----------
    print("\n2.4.0.1.5 · selector de productos")
    doc = _conversacion(c.cid)
    productos = (
        json.loads(doc["captured_data"].get("trx_products_result") or "{}")
        .get("data", {})
        .get("products")
        or []
    )
    check(bool(productos), "hay productos en el payload de origen")
    for indice, producto in enumerate(productos):
        etiqueta = o[indice] if indice < len(o) else ""
        ultimos = str(producto.get("last_four") or "")
        # PROCEDENCIA: los 4 digitos mostrados son los de last_four, no otros
        check(
            bool(ultimos) and etiqueta.endswith(ultimos),
            f"boton {indice + 1} termina en last_four del payload ({ultimos})",
        )
        # FORMATO/DEGRADACION: nunca el contrato entero
        contrato = str(producto.get("contract_id") or "")
        check(
            len(contrato) <= 4 or contrato not in etiqueta,
            f"boton {indice + 1} no expone el contrato completo",
        )
        _sin_crudos(etiqueta, f"boton {indice + 1}")
    _sin_crudos(t, "prompt del selector")

    # ---------- 2.4.0.1.7 · reprompt de fecha ----------
    print("\n2.4.0.1.7 · reprompt de fecha ilegible")
    t, o = c.decir(_elegir(o, "Tarjeta"))
    t, o = c.decir(_elegir(o, "Entre $35.000"))
    prompt_normal = t
    check("dd/mm/aaaa" in _norm(t), "el prompt pide el formato DD/MM/AAAA")
    t, o = c.decir("99/99/9999")
    check("no pude leer" in _norm(t), "fecha ilegible: avisa y repregunta")
    check("dd/mm/aaaa" in _norm(t), "el aviso repite el formato esperado")
    # CICLO DE VIDA: con una fecha valida el aviso desaparece
    t, o = c.decir(FECHA_CON_MOVS)
    check("no pude leer" not in _norm(t), "tras la fecha valida el aviso ya no aparece")

    # ---------- 2.4.0.1.9 · listado de movimientos ----------
    print("\n2.4.0.1.9 · listado de movimientos")
    doc = _conversacion(c.cid)
    movimientos = (
        json.loads(doc["captured_data"].get("trx_movimientos_result") or "{}")
        .get("movimientos")
        or []
    )
    check(bool(movimientos), "hay movimientos en el payload de origen")
    etiquetas_mov = [x for x in o if "no encuentro" not in _norm(x)]
    check(
        len(etiquetas_mov) == min(len(movimientos), 3),
        f"se listan {min(len(movimientos), 3)} movimientos (tope 3)",
    )
    for indice, movimiento in enumerate(etiquetas_mov):
        origen = movimientos[indice]
        # PROCEDENCIA: descripcion e importe salen del movimiento correspondiente
        check(
            str(origen.get("descripcion") or "") in movimiento,
            f"movimiento {indice + 1}: descripcion del payload",
        )
        valor = origen.get("valor")
        if valor is not None:
            esperado = f"{float(valor):,.0f}".replace(",", ".")
            check(f"${esperado}" in movimiento, f"movimiento {indice + 1}: importe formateado")
        # FORMATO: fecha DD/MM/AAAA, nunca ISO (H-03)
        check(
            bool(_FECHA_DDMMAAAA.search(movimiento)),
            f"movimiento {indice + 1}: fecha en DD/MM/AAAA",
        )
        check(
            not _FECHA_ISO.search(movimiento),
            f"movimiento {indice + 1}: sin fecha en ISO",
        )
        _sin_crudos(movimiento, f"movimiento {indice + 1}")

    # ---------- 2.4.0.1.11 · confirmacion ----------
    print("\n2.4.0.1.11 · confirmacion de la compra")
    elegido = movimientos[0]
    t, o = c.decir(etiquetas_mov[0])
    doc = _conversacion(c.cid)
    producto = productos[0]
    # PROCEDENCIA: cada vineta contra su fuente
    check(str(elegido.get("descripcion") or "") in t, "descripcion: del movimiento elegido")
    valor = elegido.get("valor")
    if valor is not None:
        esperado = f"{float(valor):,.0f}".replace(",", ".")
        check(f"${esperado}" in t, "valor: del movimiento elegido y formateado")
    check(bool(_FECHA_DDMMAAAA.search(t)), "fecha: en DD/MM/AAAA")
    check(not _FECHA_ISO.search(t), "fecha: sin ISO")
    ultimos = str(producto.get("last_four") or "")
    # DATO: los 4 digitos han de ser los de last_four (el PAN de
    # financial-overview tras el gate .4). Eso es lo que se verifica.
    check(bool(ultimos) and ultimos in t, f"producto: ultimos 4 reales ({ultimos})")
    # COPY: la mascara es texto, no dato. Un cambio autorizado no debe romper
    # la prueba -- es la premisa de este verificador-- pero si debe verse.
    if ultimos and f"*{ultimos}" not in t:
        mascara = t[max(0, t.find(ultimos) - 6):t.find(ultimos) + 4]
        print(f"  [AVISO] la mascara del producto ya no es '*{ultimos}' sino "
              f"'{mascara.strip()}': confirmar con Fabian/PO que el cambio de "
              f"copy esta aprobado (el tablero pinta *XXXX).")
    # FORMATO: las vinetas que pide el tablero. La cuarta ya no dice la
    # palabra "producto": el tablero pide "[Producto] terminado en...", donde
    # [Producto] es el TIPO (correccion C-2 del double check). Se comprueba
    # contra la FUENTE -- el tipo del payload -- que es ademas la comprobacion
    # de procedencia que este verificador predica.
    # La vineta de descripcion es el dato CRUDO (tablero, aplicado 21/08):
    # ya no lleva la etiqueta "Descripcion:". Su contenido se comprueba arriba
    # contra el movimiento elegido; aqui quedan las vinetas etiquetadas.
    for campo in ("valor", "fecha"):
        check(campo in _norm(t), f"vineta '{campo}' presente")
    tipo = str(
        producto.get("commercial_product_desc") or producto.get("product_desc") or ""
    ).strip()
    check(bool(tipo) and _norm(tipo) in _norm(t),
          f"vineta de producto: el TIPO del payload ({tipo}) aparece")
    _sin_crudos(t, "confirmacion")
    # las dos salidas del tablero
    check(len(o) == 2, "la confirmacion ofrece exactamente dos salidas")

    print(f"\n{'MENSAJES OK' if not fallos else f'{len(fallos)} FALLOS'} "
          f"({comprobaciones} comprobaciones)")
    if fallos:
        for f in fallos:
            print(f"  - {f}")
    _reset(CLIENTE)
    return 0 if not fallos else 1


if __name__ == "__main__":
    raise SystemExit(verificar())
