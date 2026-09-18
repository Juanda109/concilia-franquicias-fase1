#!/usr/bin/env bash
# Corre TODOS los datasets contra el agente local y publica los eventos al
# pipeline local (RabbitMQ -> Logstash -> OpenSearch), con un mismo
# CATALOG_VERSION para que las seis corridas se comparen en los tableros.
#
# Antes: el stack local arriba. Para el baseline con el LLM real:
#   LOCAL_LLM_REAL=true LOCAL_RABBITMQ_ENABLED=true \
#   LOCAL_LLM_ENDPOINT=https://genai-agentepqrs-work-llm-openai.openai.azure.com/ \
#   LOCAL_LLM_API_KEY=<clave> LOCAL_IDENTITY_CSV=identidad_grounding python scripts/run_local.py up
# (LOCAL_IDENTITY_CSV da nombres de pila al saludo, que el dataset de grounding comprueba)
#
# Uso (desde co_pqrs_benchmark/):  scripts/run_all_local.sh [sufijo-del-run]
set -euo pipefail
cd "$(dirname "$0")/.."

SUFFIX="${1:-$(date +%Y%m%d-%H%M)}"
CATALOG="$(git rev-parse --short HEAD)"
mkdir -p .data/all

run() {
  local dataset="$1" source="$2" name="$3"
  echo "== $name ($dataset, source=$source) =="
  MINIO_ENABLED=false RABBITMQ_ENABLED="${RABBITMQ_ENABLED:-true}" RABBITMQ_HOST="${RABBITMQ_HOST:-127.0.0.1}" \
  RABBITMQ_USER="${RABBITMQ_USER:-guest}" RABBITMQ_PASSWORD="${RABBITMQ_PASSWORD:-guest}" \
  API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}" \
  INPUT_JSON="datasets/$dataset.json" OUTPUT_JSON=".data/all/$name-$SUFFIX.ndjson" \
  SUMMARY_TXT=".data/all/$name-${SUFFIX}_summary.txt" RUN_NAME="$name-$SUFFIX" \
  CATALOG_VERSION="$CATALOG" ENVIRONMENT="${ENVIRONMENT:-local}" BENCHMARK_SOURCE="$source" \
  BENCHMARK_MAX_TURNS="${BENCHMARK_MAX_TURNS:-12}" \
  uv run --python 3.14 --with-requirements requirements.txt python main.py 2>&1 \
    | grep -E "casos  |aciertos|published|Traceback" | tail -3
  grep -E "precision_pct|fallos_(workflow|outcome|leak|step)|sin_resolver  " ".data/all/$name-${SUFFIX}_summary.txt" | tr -s ' ' | tr '\n' ';'; echo
}

run doble_cobro_routing   benchmark   ruteo-doble-cobro
run trx_no_reconocida_routing benchmark ruteo-tnr
run canario_rutas_criticas canario    canario
run adversarial_routing   adversarial adversarial
run bypass_flows          adversarial bypass
run grounding             grounding   grounding

# Ficha de version junto a los resultados: catalog_version (el commit) apunta a ella.
python3 ../scripts/build_release_card.py --out ".data/all/ficha-$SUFFIX"
echo "Listo. Resultados en .data/all/*-$SUFFIX*, ficha en .data/all/ficha-$SUFFIX y tableros (catalog_version=$CATALOG)."
