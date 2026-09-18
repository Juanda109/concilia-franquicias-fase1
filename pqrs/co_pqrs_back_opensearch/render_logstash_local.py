#!/usr/bin/env python3
"""Renderiza la configuracion de Logstash del IaC para el compose local.

Lee ``IaC/elk/logstash/01-configmap.yaml`` (la MISMA configuracion que corre en
OKD) y deja ``main.conf`` y ``logstash.yml`` en ``.analytics-local/`` para que
``docker-compose.analytics.yml`` los monte. La unica diferencia con OKD es el
host del OpenSearch de salida: en el cluster es el Service
``opensearch-analytics``; en local es el contenedor ``opensearch-node1`` del
``docker-compose.yml`` de esta carpeta. Todo lo demas (inputs de RabbitMQ,
filtros, ramas de salida e indices) se valida tal cual esta en el IaC.

Uso:
    python render_logstash_local.py
    docker compose -f docker-compose.analytics.yml run --rm logstash \\
        logstash --config.test_and_exit -f /usr/share/logstash/pipeline/logstash.conf
    docker compose -f docker-compose.analytics.yml up -d
"""

from __future__ import annotations

from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CONFIGMAP = HERE.parent / "IaC/elk/logstash/01-configmap.yaml"
OUT_DIR = HERE / ".analytics-local"

OKD_OPENSEARCH_HOST = "https://opensearch-analytics:9200"
LOCAL_OPENSEARCH_HOST = "https://opensearch-node1:9200"


def main() -> None:
    configmap = yaml.safe_load(CONFIGMAP.read_text())
    data = configmap["data"]

    pipeline = data["main.conf"]
    occurrences = pipeline.count(OKD_OPENSEARCH_HOST)
    if not occurrences:
        raise SystemExit(f"{CONFIGMAP}: no aparece {OKD_OPENSEARCH_HOST}; revisar el render")
    pipeline = pipeline.replace(OKD_OPENSEARCH_HOST, LOCAL_OPENSEARCH_HOST)

    # La cola persistente de 4 GB es para el pod; en local basta la de memoria.
    logstash_yml = "\n".join(
        line
        for line in data["logstash.yml"].splitlines()
        if not line.startswith(("queue.", "path.queue"))
    ) + "\n"

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "main.conf").write_text(pipeline)
    (OUT_DIR / "logstash.yml").write_text(logstash_yml)
    print(
        f"render OK -> {OUT_DIR.relative_to(HERE.parent)}/ "
        f"(host de salida {OKD_OPENSEARCH_HOST} -> {LOCAL_OPENSEARCH_HOST}, "
        f"{occurrences} salidas)"
    )


if __name__ == "__main__":
    main()
