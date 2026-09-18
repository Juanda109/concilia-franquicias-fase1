#!/usr/bin/env python3
"""Regenera IaC/backend/co_pqrs_benchmark/03-configmap-dataset.yaml desde los datasets.

La fuente de verdad son los ficheros de `DATASETS` en datasets/; el ConfigMap es
la copia que monta el CronJob del benchmark en OKD (la imagen no trae datasets/).
Cada dataset es una clave del ConfigMap, asi el Job elige cual correr con
INPUT_JSON=/data/input/<fichero>.json sin tocar el manifiesto.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASETS = (
    ROOT / "datasets/doble_cobro_routing.json",
    ROOT / "datasets/trx_no_reconocida_routing.json",
    ROOT / "datasets/adversarial_routing.json",
    ROOT / "datasets/bypass_flows.json",
    ROOT / "datasets/grounding.json",
)
DATASET = DATASETS[0]  # compatibilidad con el test de deriva
OUT = ROOT.parent / "IaC/backend/co_pqrs_benchmark/03-configmap-dataset.yaml"

HEADER = """# Datasets del benchmark completo, montados como ConfigMap (igual que el canario).
# La imagen del benchmark NO incluye la carpeta datasets/, y el lote original de
# Diego vive en MinIO (input_data/user_inputs.json). Con esto el CronJob evalua
# los casos versionados en git (ruteo de los dos flujos, adversariales, bypass y
# fidelidad a la fuente), sin
# depender de que alguien suba un fichero al bucket. El Job elige el dataset con
# INPUT_JSON=/data/input/<fichero>.json.
#
# FUENTE DE VERDAD: co_pqrs_benchmark/datasets/*.json (lista DATASETS del script).
# Este ConfigMap es una copia; el test co_pqrs_benchmark/tests/test_dataset_configmap.py
# falla si se desincronizan. Regenerar con:
#   python co_pqrs_benchmark/scripts/build_dataset_configmap.py
apiVersion: v1
kind: ConfigMap
metadata:
  name: conf-pqrs-benchmark-dataset
  labels:
    app.kubernetes.io/part-of: benchmark
data:
"""


def render() -> str:
    out = HEADER
    for dataset in DATASETS:
        cases = json.loads(dataset.read_text())
        body = json.dumps(cases, ensure_ascii=False, indent=2)
        out += f"  {dataset.name}: |\n" + textwrap.indent(body, "    ") + "\n"
    return out


def main() -> None:
    OUT.write_text(render())
    print(f"{OUT.relative_to(ROOT.parent)} regenerado")


if __name__ == "__main__":
    main()
