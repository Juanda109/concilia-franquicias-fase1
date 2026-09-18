#!/usr/bin/env python3
"""Regenera IaC/elk/opensearch-analytics/13-configmap-dashboards-objects.yaml.

Los cuatro tableros son ficheros .ndjson en el repositorio; OpenSearch Dashboards no
los conoce hasta que alguien los importa. Metiendolos en un ConfigMap, el Job de
importacion (14-job-import-dashboards.yaml) puede subirlos desde dentro del cluster,
sin que nadie necesite terminal ni descargar nada.

    python co_pqrs_benchmark/scripts/build_dashboards_configmap.py
"""

from __future__ import annotations

import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "IaC/elk/opensearch-analytics/dashboards"
OUT = ROOT / "IaC/elk/opensearch-analytics/13-configmap-dashboards-objects.yaml"
FICHEROS = (
    "pqr-benchmark-dashboard.ndjson",
    "pqr-canario-dashboard.ndjson",
    "pqr-adversarial-dashboard.ndjson",
    "pqr-grounding-dashboard.ndjson",
)

HEADER = """# Los cuatro tableros como objetos guardados, para que el Job de importacion los
# suba a OpenSearch Dashboards desde dentro del cluster.
#
# FUENTE DE VERDAD: IaC/elk/opensearch-analytics/dashboards/*.ndjson
# Regenerar con: python co_pqrs_benchmark/scripts/build_dashboards_configmap.py
apiVersion: v1
kind: ConfigMap
metadata:
  name: opensearch-dashboards-objects
  labels:
    app.kubernetes.io/part-of: elk-metrics
data:
"""


def render() -> str:
    out = HEADER
    for nombre in FICHEROS:
        cuerpo = (SRC / nombre).read_text(encoding="utf-8").rstrip("\n")
        out += f"  {nombre}: |\n" + textwrap.indent(cuerpo, "    ") + "\n"
    return out


def main() -> None:
    OUT.write_text(render(), encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"{OUT.relative_to(ROOT)} regenerado ({kb:.1f} KB de 1024 KB)")


if __name__ == "__main__":
    main()
