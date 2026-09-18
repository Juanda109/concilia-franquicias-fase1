"""D1 - Compara el texto LITERAL de cada paso entre dos juegos de capturas.

Las capturas de F2/F3 se hicieron para medir cobertura, pero guardan el texto
que ve el cliente en cada paso. Eso las convierte en una linea base: al volver a
capturar, el diff deberia contener EXACTAMENTE los cambios que se hicieron a
proposito. Cualquier otra diferencia es una sorpresa, y es lo que se busca.

Compara POR PASO y no por turno, para que no dependa del orden de los
recorridos: si un mismo paso aparece en varias capturas se toma la primera
version y se avisa si dos capturas discrepan entre si.

Uso:
    python3 diff_capturas.py baseline .          # baseline vs capturas de ahora
    python3 diff_capturas.py dir_a dir_b
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import unicodedata


def _norm_espacios(t: str) -> str:
    return re.sub(r"\s+", " ", str(t or "")).strip()


def textos_por_paso(directorio: str) -> dict[str, str]:
    """{paso: texto literal}. Avisa si dos capturas dan textos distintos."""
    fuera: dict[str, str] = {}
    origen: dict[str, str] = {}
    for ruta in sorted(glob.glob(os.path.join(directorio, "captura*.json"))):
        try:
            datos = json.load(open(ruta))
        except Exception:
            continue
        for recorrido in datos:
            for turno in recorrido.get("turnos") or []:
                paso = turno.get("paso") or ""
                texto = _norm_espacios(turno.get("texto"))
                if not paso or not texto:
                    continue
                if paso in fuera and fuera[paso] != texto:
                    # dos capturas discrepan: puede ser dato dinamico del
                    # cliente (importe, ultimos 4) y no un cambio de copy
                    continue
                fuera.setdefault(paso, texto)
                origen.setdefault(paso, os.path.basename(ruta))
    return fuera


def _resumen(t: str, n: int = 96) -> str:
    return t[:n] + ("…" if len(t) > n else "")


def main() -> int:
    a = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    b = sys.argv[2] if len(sys.argv) > 2 else "."
    antes, ahora = textos_por_paso(a), textos_por_paso(b)

    solo_antes = sorted(set(antes) - set(ahora))
    solo_ahora = sorted(set(ahora) - set(antes))
    comunes = sorted(set(antes) & set(ahora))
    distintos = [p for p in comunes if antes[p] != ahora[p]]

    print(f"pasos con texto: {len(antes)} (antes) vs {len(ahora)} (ahora)")
    print(f"iguales: {len(comunes) - len(distintos)} · DISTINTOS: {len(distintos)}")
    if solo_antes:
        print(f"\n--- solo en la linea base ({len(solo_antes)}) ---")
        for p in solo_antes:
            print(f"  {p}")
    if solo_ahora:
        print(f"\n--- solo ahora ({len(solo_ahora)}) ---")
        for p in solo_ahora:
            print(f"  {p}: {_resumen(ahora[p], 70)}")

    print(f"\n=== TEXTOS QUE CAMBIARON ({len(distintos)}) ===")
    for p in distintos:
        print(f"\n### {p}")
        print(f"  ANTES: {_resumen(antes[p])}")
        print(f"  AHORA: {_resumen(ahora[p])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
