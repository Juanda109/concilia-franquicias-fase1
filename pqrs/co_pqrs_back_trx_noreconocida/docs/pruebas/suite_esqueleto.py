"""F1 — recorre el arbol del esqueleto (2.4.0.1.x) con la matriz de 12 clientes.

Cada caso es un guion de acciones sobre la conversacion HTTP:
  pick:X       pulsa la opcion cuya etiqueta contiene X (falla si no esta)
  text:X       envia X como texto libre (fechas)
  expect:X     el ultimo texto del bot contiene X
  expect_opt:X hay una opcion que contiene X
  expect_no_opt:X  NO hay opcion que contenga X  (defectos de presentacion)

A diferencia de la suite vieja, no asume pasos estaticos: los gates reescriben
current_step y aqui solo importa lo que el bot muestra. Verifica CONTENIDO, no
solo botones. Las fechas del simulador son absolutas: con movimientos, 06/08/2026.
"""

from __future__ import annotations

import re
import sys
import unicodedata

from runner import Conversacion

FRASE = "No reconozco esta compra"


def _limpiar_caso(uid: str) -> None:
    """Borra el caso durable del cliente para que la recurrencia-bot no
    arrastre la entrada de un caso anterior de esta misma corrida/dia."""
    import ssl, urllib.request
    ctx = ssl.create_default_context(); ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        f"https://localhost:9200/trx-no-reconocida-cases/_doc/{uid}",
        method="DELETE", headers={"Authorization": "Basic YWRtaW46YWRtaW4="})
    try:
        urllib.request.urlopen(req, context=ctx, timeout=5)
    except Exception:
        pass


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


# Tramo comun hasta el gate de productos (todos los clientes que no recurren).
# Validacion silenciosa (ajuste 13/08): tras el suceso 4 el gate valida la
# recurrencia en el mismo turno y salta directo a la cantidad -- sin mensaje
# "Estoy validando..." ni turno de Continuar.
COMUN = [
    "pick:presencial o por internet",
    "expect:cuantas transacciones",
    "expect_no_opt:continuar",
    "pick:1",
    "expect:una transaccion a la vez",
    "pick:empezar ahora",
    "expect:datos de contacto",
    "pick:si, continuar",
]

# El gate 2.4.0.1.4 corre dentro del turno del "Si, continuar": el selector
# (o el exit de sin-productos) aparece de inmediato, sin turno intermedio.
HASTA_LISTADO = COMUN + [
    "expect:selecciona la cuenta o tarjeta",
    "pick:tarjeta",                # unico producto por cliente en la matriz
    "expect:rango de valor",
    "pick:entre $35.000",
    "expect:dd/mm/aaaa",           # 2.4.0.1.7 pide la fecha en el formato del tablero
]

CASOS: list[tuple[str, str, list[str]]] = [
    ("A · recurrencia Salesforce -> PQR", "1013634958", [
        "pick:presencial o por internet",
        "expect:gestion reciente",
        "expect_opt:formulario pqr",
    ]),
    ("B · card_flag=false -> sin productos (.4.exit)", "1013634959", COMUN + [
        "expect:no tienes productos activos",
        "expect:app bbva",              # copy del tablero, no el del excel viejo
        "expect_opt:terminar",
    ]),
    ("J · Mas de 3 -> formulario (.1.1.pqr)", "98787954", [
        "pick:presencial o por internet",
        "expect:cuantas transacciones",
        "pick:mas de 3",
        "expect:formulario",
        "expect_opt:formulario pqr",
    ]),
    ("H · MASTERCARD vencida (.7.exit) sin consultar ASO", "1013634965", HASTA_LISTADO + [
        "text:01/01/2025",
        "expect:supera el plazo permitido por las franquicias",
        "expect_opt:terminar",
    ]),
    ("I · transactions vacio -> .8.return con TRES salidas", "1013634966", HASTA_LISTADO + [
        "text:06/08/2026",
        "expect:no encontramos compras registradas",
        "expect_opt:elegir otra fecha",
        "expect_opt:seleccionar otro producto",
        "expect_opt:terminar consulta",
        "pick:elegir otra fecha",
        "expect:fecha",
        "text:05/08/2026",
        "expect:no encontramos compras registradas",
        "pick:seleccionar otro producto",
        "expect:selecciona la cuenta o tarjeta",
    ]),
    ("C · feliz: 3 movs, formato de label, confirmacion, devolucion", "1013634960",
     HASTA_LISTADO + [
        "text:06/08/2026",
        "expect:selecciona",
        "expect_opt:compra falabella",
        "expect_opt:no encuentro la transaccion",   # con 3 movs SI debe estar
        # -- desvio: .9.exit y reenganche a nueva fecha --
        "pick:no encuentro la transaccion",
        "expect_opt:seleccionar una nueva fecha",
        "pick:seleccionar una nueva fecha",
        "expect:fecha",
        "text:05/08/2026",                       # dia sin movs: reconsulta valida
        "expect:no encontramos compras registradas",
        "pick:elegir otra fecha",
        "expect:fecha",
        "text:06/08/2026",                       # vuelta al listado
        "expect_opt:compra falabella",
        "pick:falabella",
        "expect:confirma los datos de la compra",
        "expect_opt:si, continuar con el reporte",
        "expect_opt:ya reconozco la transaccion",
        # ---- frontera: tras confirmar, el gate .12 (pendiente=false) debe
        # entregar a Luis en la pregunta de investigacion (.13). Su tramo
        # (bloqueo -> .19 -> devolucion) no se verifica aqui.
        "pick:si, continuar con el reporte",
        "expect:iniciar con la investigacion",
        "expect_opt:si, continuar con la investigacion",
    ]),
    ("D · 1 mov: la salida 'No encuentro' TAMBIEN existe (H-02 corregido)",
     "1013634961", HASTA_LISTADO + [
        "text:06/08/2026",
        # Antes solo aparecia con exactamente 3 movimientos, por las keys
        # posicionales del YAML: con 1 o 2, la salida era inalcanzable.
        "expect_opt:no encuentro la transaccion",
        "pick:compra",
        "expect:confirma los datos de la compra",
        # eci=1 -> PQR ocurre en .19, tras el bloqueo: tramo de Luis. Aqui solo
        # se verifica la entrega en la frontera.
        "pick:si, continuar con el reporte",
        "expect:iniciar con la investigacion",
    ]),
    ("G · pendiente TDC -> .12.exit", "1013634964", HASTA_LISTADO + [
        "text:06/08/2026",
        "pick:compra",
        "expect:confirma los datos de la compra",
        "pick:si, continuar con el reporte",
        "expect:estado pendiente",
        "expect_opt:terminar",
    ]),
    ("S1 · suceso cambiazo -> formulario (2.4.1)", "1013634962", [
        "pick:cambiazo",
        "expect_opt:formulario pqr",
    ]),
    ("S2 · suceso hurto o perdida -> formulario (2.4.2)", "1013634963", [
        "pick:hurto o perdida",
        "expect_opt:formulario pqr",
    ]),
    ("S3 · suceso datos obtenidos -> formulario (2.4.3)", "1013634964", [
        "pick:obtuvo tus datos",
        "expect_opt:formulario pqr",
    ]),
    ("R1 · rango Menor a $35.000 -> formulario (.6.pqr)", "1013634963",
     COMUN + [
        "expect:selecciona la cuenta o tarjeta",
        "pick:tarjeta",
        "expect:rango de valor",
        "pick:menor a $35.000",
        "expect_opt:formulario pqr",
    ]),
    ("R2 · rango Mayor a $500.000 -> formulario (.6.pqr)", "1013634962",
     COMUN + [
        "expect:selecciona la cuenta o tarjeta",
        "pick:tarjeta",
        "expect:rango de valor",
        "pick:mayor a $500.000",
        "expect_opt:formulario pqr",
    ]),
    ("R3 · 'No es necesario, ya reconozco' cierra por feedback", "10482895",
     HASTA_LISTADO + [
        "text:06/08/2026",
        "pick:compra",
        "expect:confirma los datos de la compra",
        "pick:ya reconozco la transaccion",
        "expect_opt:me ayudo",       # el copy de feedback rota entre 3 variantes
    ]),
    ("R4 · 'Finalizar conversacion' en datos de contacto (.3)", "01576905",
     COMUN[:-1] + [
        "pick:finalizar conversacion",
        "expect_opt:me ayudo",       # idem: anclar al boton, no al copy rotatorio
    ]),
    ("C2 · fecha valida SIN movimientos: ¿el simulador filtra por fecha?",
     "10482895", HASTA_LISTADO + [
        "text:05/08/2026",
        "expect:no encontramos compras registradas",  # si lista igual, el sim ignora la fecha
    ]),
    ("P1 · fecha ilegible en 2.4.0.1.7 repregunta y luego acepta la buena",
     "01576905", HASTA_LISTADO + [
        "text:99/99/9999",
        "expect:no pude leer esa fecha",
        "text:hola",
        "expect:no pude leer esa fecha",
        "text:06/08/2026",
        "expect:selecciona la compra",   # tras corregir, la consulta sale con la fecha buena
    ]),
]


def ejecutar(solo: str | None = None) -> None:
    total_ok = total_ko = 0
    for titulo, uid, guion in CASOS:
        if solo and solo not in titulo:
            continue
        _limpiar_caso(uid)
        c = Conversacion(uid)
        print(f"\n{'=' * 76}\n{titulo}   (user_id {uid})\n{'=' * 76}")
        if not c.abrir():
            print(f"  NO ARRANCA: {c.error}")
            total_ko += 1
            continue
        t, o = c.decir(FRASE)
        fallo = None
        for accion in guion:
            verbo, _, arg = accion.partition(":")
            argn = _norm(arg)
            if verbo == "pick":
                elegida = next((x for x in o if argn in _norm(x)), None)
                if not elegida and argn.startswith("tarjeta"):
                    # solo-FO: la etiqueta del selector es el nombre real del
                    # producto; se elige la primera opcion con mascara.
                    elegida = next((x for x in o if "•" in x), None)
                if not elegida:
                    fallo = f"pick '{arg}' no esta en {o}"
                    break
                t, o = c.decir(elegida)
                if c.error:
                    fallo = c.error
                    break
            elif verbo == "text":
                t, o = c.decir(arg)
                if c.error:
                    fallo = c.error
                    break
            elif verbo == "expect":
                if argn not in _norm(t):
                    fallo = f"esperaba '{arg}' en: {' '.join((t or '').split())[:140]}"
                    break
            elif verbo == "expect_opt":
                if not any(argn in _norm(x) for x in o):
                    fallo = f"esperaba opcion '{arg}' en {o}"
                    break
            elif verbo == "expect_no_opt":
                if any(argn in _norm(x) for x in o):
                    fallo = f"NO esperaba opcion '{arg}' y esta: {o}"
                    break
        if fallo:
            print(f"  [FALLA] {fallo}")
            print(f"  contexto> {' '.join((t or '').split())[:180]}")
            if o:
                print(f"  OPC: {o}")
            total_ko += 1
        else:
            print(f"  [OK] {len(guion)} acciones")
            print(f"  final> {' '.join((t or '').split())[:160]}")
            if o:
                print(f"  OPC: {o[:4]}")
            total_ok += 1
    print(f"\n{'=' * 76}\nCASOS: {total_ok} OK · {total_ko} FALLAN\n{'=' * 76}")


if __name__ == "__main__":
    ejecutar(sys.argv[1] if len(sys.argv) > 1 else None)
