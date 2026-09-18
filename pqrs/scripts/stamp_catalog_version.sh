#!/usr/bin/env bash
# Estampa la version evaluada en los dos sitios que la publican a la analitica:
#   - conf-pqrs-benchmark-env  (corridas lanzadas por los CronJobs y por Jobs puntuales)
#   - deployment del front     (corridas lanzadas desde la vista Benchmark)
# Sin esto las corridas se publican como "unknown" y la evidencia de trazabilidad no prueba nada.
#
# Uso:  scripts/stamp_catalog_version.sh [commit]     (por defecto, el HEAD actual)
set -euo pipefail
cd "$(dirname "$0")/.."

SHA="${1:-$(git rev-parse --short HEAD)}"
CM="IaC/backend/co_pqrs_benchmark/00-configmap.yaml"
FRONT="IaC/frontend/co_pqrs_front_test/01-deployment.yaml"

sed -i '' -E "s#^(  CATALOG_VERSION: )\".*\"#\\1\"$SHA\"#" "$CM"
sed -i '' -E "/- name: CATALOG_VERSION/{n;s#^([[:space:]]*value: ).*#\\1$SHA#;}" "$FRONT"

echo "Version estampada: $SHA"
grep -n 'CATALOG_VERSION' -A1 "$CM" | tail -2
grep -n 'CATALOG_VERSION' -A1 "$FRONT" | tail -2
echo
echo "Aplicar para que surta efecto:"
echo "  oc apply -k IaC/"
echo "  oc -n pqr-genai-dev rollout restart deploy/co-pqrs-front-test"
