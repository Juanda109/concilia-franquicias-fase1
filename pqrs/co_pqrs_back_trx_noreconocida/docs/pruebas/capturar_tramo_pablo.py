"""F2 - Captura los recorridos de MI tramo (hasta 2.4.0.1.11), para el medidor.

Complementa a capturar_tramo_luis.py. Juntas, las dos capturas dan la cobertura
real del flujo entero cuando se pasan a cobertura_txnr.py.

Cada recorrido apunta a aristas concretas que el medidor daba por no pisadas:
los tres sucesos que no son "compra", las cantidades, el selector con varios
productos, los rangos de importe, las salidas tempranas y los reenganches.

Uso:  python3 -u capturar_tramo_pablo.py             -> todos, captura_tramo_pablo.json
      python3 -u capturar_tramo_pablo.py Q1,Q2,Q3   -> solo esos, captura_tramo_pablo_Q1.json

Conviene correrlo POR LOTES: cada recorrido son varios turnos con sondeo y el
entorno local corta los procesos largos. cobertura_txnr.py suma todas las
capturas que encuentre, asi que partirlo no pierde nada.
"""

from __future__ import annotations

import json
import sys

from capturar_tramo_luis import _elegir, _norm, _paso_real, _reset  # noqa: F401

# OJO: _elegir devuelve (etiqueta, si_caso_con_boton), no una cadena.
from runner import Conversacion

# (id, cliente, pasos, que arista(s) se busca cubrir)
RECORRIDOS = [
    ("Q1", "1013634962", ["No reconozco esta compra", "Me cambiaron la tarjeta"],
     "2.4.0 -> 2.4.1 (cambiazo)"),
    ("Q2", "1013634963", ["No reconozco esta compra", "Hurto o perdida"],
     "2.4.0 -> 2.4.2 (hurto)"),
    ("Q3", "1013634964", ["No reconozco esta compra", "Alguien obtuvo tus datos"],
     "2.4.0 -> 2.4.3 (suplantacion)"),
    ("Q4", "98787954", ["No reconozco esta compra", "Compra presencial", "Mas de 3",
                        "Formulario PQR"],
     "2.4.0.1.1 -> .1.pqr -> satisfaction"),
    ("Q5", "10482895", ["No reconozco esta compra", "Compra presencial", "3",
                        "Empezar ahora"],
     "2.4.0.1.1 [3] -> 2.4.0.1.2"),
    ("Q6", "1013634962", ["No reconozco esta compra", "Compra presencial", "1",
                          "Empezar ahora", "Si, continuar", "Tarjeta",
                          "Mayor a $500.000", "Formulario PQR"],
     "2.4.0.1.6 [mayor] -> .6.pqr -> satisfaction"),
    ("Q7", "1013634963", ["No reconozco esta compra", "Compra presencial", "1",
                          "Empezar ahora", "Si, continuar", "Tarjeta",
                          "Menor a $35.000", "Formulario PQR"],
     "2.4.0.1.6 [menor] -> .6.pqr"),
    ("Q8", "1013634959", ["No reconozco esta compra", "Compra presencial", "1",
                          "Empezar ahora", "Si, continuar", "Terminar"],
     "2.4.0.1.4.exit -> satisfaction (cliente sin productos)"),
    ("Q9", "1013634965", ["No reconozco esta compra", "Compra presencial", "1",
                          "Empezar ahora", "Si, continuar", "Tarjeta",
                          "Entre $35.000", "01/01/2025", "Terminar"],
     "2.4.0.1.7.exit -> satisfaction (fuera de plazo)"),
    ("Q10", "1013634966", ["No reconozco esta compra", "Compra presencial", "1",
                           "Empezar ahora", "Si, continuar", "Tarjeta",
                           "Entre $35.000", "06/08/2026", "Elegir otra fecha",
                           "05/08/2026"],
     "2.4.0.1.8.return [otra fecha] -> 2.4.0.1.7"),
    ("Q11", "1013634966", ["No reconozco esta compra", "Compra presencial", "1",
                           "Empezar ahora", "Si, continuar", "Tarjeta",
                           "Entre $35.000", "06/08/2026", "Seleccionar otro producto"],
     "2.4.0.1.8.return [otro producto] -> 2.4.0.1.5"),
    ("Q12", "1013634966", ["No reconozco esta compra", "Compra presencial", "1",
                           "Empezar ahora", "Si, continuar", "Tarjeta",
                           "Entre $35.000", "06/08/2026", "Terminar consulta"],
     "2.4.0.1.8.return [terminar] -> satisfaction"),
    ("Q13", "1013634960", ["No reconozco esta compra", "Compra presencial", "1",
                           "Empezar ahora", "Si, continuar", "Tarjeta",
                           "Entre $35.000", "06/08/2026", "No encuentro",
                           "Elegir otra fecha"],
     "2.4.0.1.9 [no encuentro] -> .9.exit"),
    ("Q14", "1013634961", ["No reconozco esta compra", "Compra presencial", "1",
                           "Empezar ahora", "Si, continuar", "Tarjeta",
                           "Entre $35.000", "06/08/2026", "@movimiento",
                           "No es necesario, ya reconozco"],
     "2.4.0.1.11 [ya reconozco] -> satisfaction"),
    ("Q15", "1013634968", ["No reconozco esta compra", "Compra presencial", "1",
                           "Empezar ahora", "Si, continuar", "Tarjeta",
                           "Entre $35.000", "06/08/2026", "@movimiento"],
     "selector/listado con muchos movimientos (posiciones 2..5)"),
]


def recorrer(rid: str, uid: str, pasos: list[str], proposito: str) -> dict:
    _reset(uid)
    c = Conversacion(uid)
    if not c.abrir():
        return {"id": rid, "uid": uid, "proposito": proposito, "error": c.error, "turnos": []}
    turnos: list[dict] = []
    o: list[str] = []
    for paso in pasos:
        if paso == "@movimiento":
            movs = [x for x in o if "no encuentro" not in _norm(x)]
            etiqueta = movs[0] if movs else paso
        else:
            etiqueta, _ = _elegir(o, paso)
        t, o = c.decir(etiqueta)
        turnos.append({
            "pedido": paso, "enviado": etiqueta, "paso": _paso_real(c.cid),
            "texto": " ".join((t or "").split()), "opciones": list(o),
        })
        if c.error:
            turnos[-1]["error"] = c.error
            break
    _reset(uid)
    return {"id": rid, "uid": uid, "proposito": proposito, "turnos": turnos}


if __name__ == "__main__":
    filtro = set((sys.argv[1] if len(sys.argv) > 1 else "").split(",")) - {""}
    salida = []
    for rid, uid, pasos, prop in RECORRIDOS:
        if filtro and rid not in filtro:
            continue
        r = recorrer(rid, uid, pasos, prop)
        ultimo = (r["turnos"] or [{}])[-1]
        print(f"{rid:<5}{uid:<12}turnos={len(r['turnos']):<3}"
              f"paso_final={str(ultimo.get('paso')):<22}{prop[:40]}")
        salida.append(r)
    sufijo = f"_{sorted(filtro)[0]}" if filtro else ""
    with open(f"captura_tramo_pablo{sufijo}.json", "w") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)
    print(f"\n-> captura_tramo_pablo{sufijo}.json")
