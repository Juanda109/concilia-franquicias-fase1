"""F3 - Recorridos dirigidos a las aristas que el medidor daba por no pisadas.

Cada recorrido apunta a una o varias aristas concretas de la lista que emite
cobertura_txnr.py. Los que llevan "caida" detienen el servicio trx en el turno
indicado para provocar la ruta de error, y lo restauran despues.

Uso (POR LOTES, el entorno corta procesos largos):
    python3 -u capturar_f3.py E1,E2,E3      -> captura_f3_E1.json
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

from capturar_tramo_luis import _elegir, _norm, _paso_real, _reset
from runner import Conversacion

BASE = ["No reconozco esta compra", "Compra presencial", "1", "Empezar ahora", "Si, continuar"]
HASTA_FECHA = BASE + ["Tarjeta", "Entre $35.000"]

# (id, cliente, pasos, turno_en_que_cae_el_servicio | None, que cubre)
RECORRIDOS = [
    ("E1", "1013634961", BASE, 4,
     "2.4.0.1.4.error: ASO caido al pedir productos"),
    ("E2", "1013634961", HASTA_FECHA + ["06/08/2026"], 7,
     "2.4.0.1.8.error: ASO caido al pedir movimientos"),
    ("E3", "1013634960", HASTA_FECHA + ["06/08/2026", "@movimiento"], 8,
     "2.4.0.1.10.pqr: ASO caido al pedir el detalle"),
    ("E4", "1010223694", BASE + ["@producto2"], None,
     "2.4.0.1.5 [Producto 2]: cliente con TDC + Pasivo"),
    ("E5", "1013634968", HASTA_FECHA + ["06/08/2026", "@movimiento2"], None,
     "2.4.0.1.9 [Movimiento 2]"),
    ("E6", "1013634968", HASTA_FECHA + ["06/08/2026", "@movimiento3"], None,
     "2.4.0.1.9 [Movimiento 3]"),
    ("E7", "1013634968", HASTA_FECHA + ["06/08/2026", "@movimiento4"], None,
     "2.4.0.1.9 [Movimiento 4]"),
    ("E8", "1013634968", HASTA_FECHA + ["06/08/2026", "@movimiento5"], None,
     "2.4.0.1.9 [Movimiento 5]"),
    ("E9", "1013634960", HASTA_FECHA + ["06/08/2026", "No encuentro",
                                        "Seleccionar una nueva fecha"], None,
     "2.4.0.1.9.exit [nueva fecha] -> 2.4.0.1.7"),
    ("E10", "1013634961", HASTA_FECHA + ["06/08/2026", "No encuentro",
                                         "No, finalizar"], None,
     "2.4.0.1.9.exit [finalizar] -> satisfaction"),
    ("E11", "1013634962", ["No reconozco esta compra", "Me cambiaron la tarjeta",
                           "Formulario PQR"], None,
     "2.4.1 [Formulario PQR] -> satisfaction"),
    ("E12", "1013634958", ["No reconozco esta compra", "Compra presencial",
                           "Formulario PQR"], None,
     "2.4.0.pqr_recurrencia -> satisfaction"),
    ("E13", "1013634970", ["No reconozco esta compra", "Compra presencial", "2",
                           "Empezar ahora", "Si, continuar", "Tarjeta",
                           "Entre $35.000", "06/08/2026", "@movimiento",
                           "Si, continuar con el reporte", "Si, continuar con la investigacion",
                           "Si, bloquear definitivamente", "Si, bloquear y continuar",
                           "Continuar", "Continuar", "Continuar",
                           "Si, reportar la siguiente"], None,
     "2.4.0.1.20.1 [reportar siguiente] -> 2.4.0.1.3"),
    # --- segunda tanda: cerrar las 11 que quedaban ---
    ("E14", "1013634973", BASE + ["@producto3"], None, "2.4.0.1.5 [Producto 3] (cliente P, 5 productos)"),
    ("E15", "1013634973", BASE + ["@producto4"], None, "2.4.0.1.5 [Producto 4]"),
    ("E16", "1013634973", BASE + ["@producto5"], None, "2.4.0.1.5 [Producto 5]"),
    ("E17", "1013634961", BASE + ["Formulario PQR"], 4, "2.4.0.1.4.error [Formulario PQR] -> satisfaction"),
    ("E18", "1013634961", HASTA_FECHA + ["06/08/2026", "Formulario PQR"], 7,
     "2.4.0.1.8.error [Formulario PQR] -> satisfaction"),
    ("E19", "1013634960", HASTA_FECHA + ["06/08/2026", "@movimiento", "Formulario PQR"], 8,
     "2.4.0.1.10.pqr [Formulario PQR] -> satisfaction"),
    ("E20", "1013634963", ["No reconozco esta compra", "Hurto o perdida", "Formulario PQR"], None,
     "2.4.2 [Formulario PQR] -> satisfaction"),
    ("E21", "1013634964", ["No reconozco esta compra", "Alguien obtuvo tus datos", "Formulario PQR"], None,
     "2.4.3 [Formulario PQR] -> satisfaction"),
    ("E22", "1013634972", HASTA_FECHA + ["06/08/2026", "@movimiento",
                                         "Si, continuar con el reporte",
                                         "Si, continuar con la investigacion",
                                         "No, bloquear temporalmente",
                                         "Si, apagar temporalmente", "Formulario PQR"], 11,
     "2.4.0.1.16.1.pqr: bloqueo temporal falla"),
    ("E23", "1013634970", HASTA_FECHA + ["06/08/2026", "@movimiento",
                                         "Si, continuar con el reporte",
                                         "Si, continuar con la investigacion",
                                         "Si, bloquear definitivamente",
                                         "Si, bloquear y continuar", "Formulario PQR"], 11,
     "2.4.0.1.17.1.pqr: bloqueo permanente falla"),
    ("E24", "1013634970", ["No reconozco esta compra", "Compra presencial", "2",
                           "Empezar ahora", "Si, continuar", "Tarjeta", "Entre $35.000",
                           "06/08/2026", "@movimiento", "Si, continuar con el reporte",
                           "Si, continuar con la investigacion", "Si, bloquear definitivamente",
                           "Si, bloquear y continuar", "Continuar", "Continuar", "Continuar",
                           "Si, reportar la siguiente", "Si, continuar", "Tarjeta",
                           "Entre $35.000", "06/08/2026", "@movimiento",
                           "Si, continuar con el reporte", "Si, continuar con la investigacion",
                           "Continuar", "Continuar", "Continuar", "Terminar"], None,
     "2.4.0.1.20.2 [Terminar] -> satisfaction (cierre del bucle)"),
]


def _pulsar(o: list[str], paso: str) -> str:
    """Traduce las marcas @movimientoN / @productoN a la opcion en esa posicion."""
    if paso.startswith("@movimiento"):
        movs = [x for x in o if "no encuentro" not in _norm(x)]
        n = paso.replace("@movimiento", "") or "1"
        i = int(n) - 1
        return movs[i] if i < len(movs) else (movs[-1] if movs else paso)
    if paso.startswith("@producto"):
        i = int(paso.replace("@producto", "") or "1") - 1
        return o[i] if i < len(o) else (o[-1] if o else paso)
    etiqueta, _ = _elegir(o, paso)
    return etiqueta


def recorrer(rid, uid, pasos, caida, proposito) -> dict:
    _reset(uid)
    c = Conversacion(uid)
    if not c.abrir():
        return {"id": rid, "uid": uid, "proposito": proposito, "error": c.error, "turnos": []}
    turnos: list[dict] = []
    o: list[str] = []
    caido = False
    try:
        for i, paso in enumerate(pasos):
            if caida is not None and i == caida:
                subprocess.run(["docker", "stop", "trx-esqueleto"], capture_output=True)
                time.sleep(2)
                caido = True
            etiqueta = _pulsar(o, paso)
            t, o = c.decir(etiqueta)
            turnos.append({
                "pedido": paso, "enviado": etiqueta, "paso": _paso_real(c.cid),
                "texto": " ".join((t or "").split()), "opciones": list(o),
            })
            if c.error:
                turnos[-1]["error"] = c.error
                break
    finally:
        if caido:
            subprocess.run(["docker", "start", "trx-esqueleto"], capture_output=True)
            time.sleep(10)
    _reset(uid)
    return {"id": rid, "uid": uid, "proposito": proposito, "turnos": turnos}


if __name__ == "__main__":
    filtro = set((sys.argv[1] if len(sys.argv) > 1 else "").split(",")) - {""}
    salida = []
    for rid, uid, pasos, caida, prop in RECORRIDOS:
        if filtro and rid not in filtro:
            continue
        r = recorrer(rid, uid, pasos, caida, prop)
        ultimo = (r["turnos"] or [{}])[-1]
        print(f"{rid:<5}{uid:<12}turnos={len(r['turnos']):<3}"
              f"final={str(ultimo.get('paso')):<24}{prop[:44]}")
        salida.append(r)
    sufijo = f"_{sorted(filtro)[0]}" if filtro else ""
    with open(f"captura_f3{sufijo}.json", "w") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)
    print(f"\n-> captura_f3{sufijo}.json")
