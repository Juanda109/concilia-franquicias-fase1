"""F2 - Mide la cobertura REAL del flujo TXNR, arista por arista.

Por que hace falta: hasta ahora la cobertura se estimaba por casos ("17 casos
OK"), y eso no dice que caminos quedan sin pisar. El grafo tiene 48 pasos y 75
aristas; saber cuales faltan es lo que convierte una pasada de pruebas en un
plan y no en una sensacion.

Dos trampas que este medidor evita, ambas sufridas:

  1. EL DENOMINADOR ES FALSO. Hay aristas declaradas en el YAML que no se pintan
     nunca: su paso lleva una accion que reescribe current_step y devuelve, asi
     que el boton no llega a existir. Contarlas hace que el 100% sea imposible.
     Aqui se marcan aparte y no cuentan.

  2. EMPAREJAR POR TEXTO NO VALE. Muchos pasos generan su mensaje desde Python
     (mostrar_bloqueo_*, mostrar_trx_*), asi que el "question" del YAML no
     coincide con lo que ve el cliente. Medir asi dio una vez 4/26 cuando la
     cobertura real era 16/26. Se usa el current_step que queda en OpenSearch.

Uso:
    python3 cobertura_txnr.py                    # analiza las capturas que haya
    python3 cobertura_txnr.py captura_a.json ... # analiza las que se le indiquen

Lee las capturas producidas por capturar_tramo_luis.py (y cualquier otra con el
mismo formato: lista de recorridos con turnos que traen "paso" y "enviado").
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import unicodedata

import yaml

AQUI = os.path.dirname(os.path.abspath(__file__))
YAML_FLUJO = os.path.normpath(os.path.join(
    AQUI, "..", "..", "..",
    "co_pqrs_back_agent/src/domain/workflow/trx_no_reconocida/trx_no_reconocida.yml",
))
CHAT_SERVICE = os.path.normpath(os.path.join(
    AQUI, "..", "..", "..",
    "co_pqrs_back_agent/src/application/chat/chat_service.py",
))


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def cargar_grafo() -> tuple[dict, list[tuple[str, str, str]]]:
    pasos = yaml.safe_load(open(YAML_FLUJO))["steps"]
    aristas = [
        (k, str(o.get("label")), str(o.get("next_step")))
        for k, s in pasos.items()
        for o in (s.get("options") or [])
    ]
    return pasos, aristas


def gates_incondicionales(pasos: dict) -> set[str]:
    """Pasos cuyo gate SIEMPRE reescribe current_step: su boton no se pinta.

    Se detecta sobre el codigo: dentro del bloque 'if step == X' del prefetch,
    una asignacion a current_step que no cuelgue de un 'if' anidado. Es una
    heuristica; los casos dudosos se marcan como tal y se confirman al medir
    (si el paso llega a renderizarse en alguna captura, no es incondicional).
    """
    codigo = open(CHAT_SERVICE, encoding="utf-8", errors="replace").read()
    constantes = dict(re.findall(r'^(_TRX_[A-Z_0-9]+) = "([^"]+)"', codigo, re.M))
    gates: set[str] = set()
    # Dos formas: por constante (if step == _TRX_X) y por literal
    # (if step == "2.4.0.1"). La segunda se me escapo en la primera version y
    # dejaba una arista muerta contada como cubrible: el paso 2.4.0.1, que
    # siempre reescribe -a PQR si hay recurrencia, a .1.1 si no- y por eso
    # nunca se renderiza.
    for m in re.finditer(r'\n    if step == (_TRX_[A-Z_0-9]+|"[0-9.a-z_]+"):\n', codigo):
        bruto = m.group(1)
        paso = bruto.strip('"') if bruto.startswith('"') else constantes.get(bruto)
        if not paso or paso not in pasos:
            continue
        # cuerpo del bloque: hasta el siguiente 'if step ==' o def de nivel 0
        resto = codigo[m.end():]
        corte = re.search(r'\n    if step == _TRX_|\n(?:async )?def ', resto)
        cuerpo = resto[: corte.start()] if corte else resto
        # asignacion a 8 espacios = nivel del bloque, sin if anidado
        if re.search(r'\n        conversation\.current_step = ', cuerpo):
            gates.add(paso)
    return gates


def gates_por_evidencia(pasos: dict, aristas: list, vistos: set) -> set[str]:
    """Gates que la heuristica no ve, deducidos de las capturas.

    Si un paso tiene ACCION, su destino SI se ha renderizado y el paso en si
    NUNCA, es que el gate lo salta siempre. Cubre el caso que el analisis
    estatico no pilla: un if/else donde AMBAS ramas asignan current_step -esas
    asignaciones van a 12 espacios, no a 8-. Es lo que pasa con 2.4.0.1.

    Es evidencia, no adivinanza: se exige haber llegado al destino.
    """
    deducidos: set[str] = set()
    for k, s in pasos.items():
        if not s.get("action") or k in vistos:
            continue
        destinos = {str(o.get("next_step")) for o in (s.get("options") or [])}
        if destinos & vistos:
            deducidos.add(k)
    return deducidos


def aristas_de_capturas(rutas: list[str], aristas: list, pasos: dict) -> tuple[set, set]:
    """Devuelve (aristas pisadas, pasos renderizados).

    El emparejamiento es por etiqueta y, si falla, POR POSICION. Hace falta
    porque los pasos con etiquetas dinamicas -el selector de productos y el
    listado de movimientos- declaran en el YAML "Producto 1", "Movimiento 1"...
    y el cliente ve "Tarjeta de Credito *0060" o "COMPRA FALABELLA - $120.000".
    Emparejar solo por texto daba esas ~10 aristas por no cubiertas para
    siempre, y hundia el porcentaje sin motivo.
    """
    pisadas: set = set()
    vistos: set = set()
    por_paso: dict[str, list] = {}
    for (a, lab, nx) in aristas:
        por_paso.setdefault(a, []).append((a, lab, nx))

    for ruta in rutas:
        try:
            datos = json.load(open(ruta))
        except Exception as exc:  # pragma: no cover
            print(f"  ! no pude leer {os.path.basename(ruta)}: {exc}")
            continue
        for recorrido in datos:
            previo = None
            opciones_previas: list[str] = []
            for turno in recorrido.get("turnos") or []:
                paso = turno.get("paso") or ""
                if paso:
                    vistos.add(paso)
                if previo:
                    env = _norm(turno.get("enviado"))
                    candidatas = por_paso.get(previo) or []
                    hit = next((c for c in candidatas if _norm(c[1]) == env), None)
                    if hit is None and opciones_previas:
                        # por posicion: donde estaba el boton que se pulso
                        idx = next(
                            (i for i, o in enumerate(opciones_previas) if _norm(o) == env),
                            None,
                        )
                        if idx is not None and idx < len(candidatas):
                            hit = candidatas[idx]
                    if hit:
                        pisadas.add(hit)
                previo = paso
                opciones_previas = list(turno.get("opciones") or [])
    return pisadas, vistos


def main() -> int:
    pasos, aristas = cargar_grafo()
    rutas = sys.argv[1:] or sorted(glob.glob(os.path.join(AQUI, "captura*.json")))
    if not rutas:
        print("No hay capturas que analizar. Genera una con capturar_tramo_luis.py")
        return 1
    pisadas, vistos = aristas_de_capturas(rutas, aristas, pasos)

    gates = gates_incondicionales(pasos) | gates_por_evidencia(pasos, aristas, vistos)
    muertas = {(a, l, n) for (a, l, n) in aristas if a in gates}

    # Una arista "muerta" que SI se piso no era muerta: la heuristica fallo.
    falsas_muertas = muertas & pisadas
    muertas -= falsas_muertas
    vivas = [x for x in aristas if x not in muertas]
    cubiertas = [x for x in vivas if x in pisadas]

    print(f"capturas analizadas: {len(rutas)}")
    for r in rutas:
        print(f"   {os.path.basename(r)}")
    print(f"\nPASOS   {len(vistos & set(pasos))}/{len(pasos)} renderizados")
    print(f"ARISTAS {len(cubiertas)}/{len(vivas)} cubiertas "
          f"({100*len(cubiertas)//max(len(vivas),1)}%)  "
          f"[{len(muertas)} muertas excluidas del denominador]")
    if falsas_muertas:
        print(f"\n  (la heuristica marco {len(falsas_muertas)} arista(s) como muertas "
              f"y si se pisaron: se corrigen solas)")

    print(f"\n--- ARISTAS MUERTAS ({len(muertas)}): declaradas pero nunca pintadas ---")
    for a, l, n in sorted(muertas):
        print(f"  {a:<22} [{l[:34]}]")

    faltan = [x for x in vivas if x not in pisadas]
    print(f"\n--- SIN PISAR ({len(faltan)}) ---")
    for a, l, n in sorted(faltan):
        alcanzable = "paso renderizado" if a in vistos else "paso NUNCA renderizado"
        print(f"  {a:<22} [{l[:34]:<36}] -> {n:<22} ({alcanzable})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
