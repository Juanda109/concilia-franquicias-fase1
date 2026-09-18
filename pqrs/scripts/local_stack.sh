#!/usr/bin/env bash
#
# local_stack.sh — Levanta el stack local de agentepqr con Docker o Podman en
# modo FALLBACK (sin API key del LLM) para probar todos los módulos + el front.
#
# Módulos (los que tienen compose): OpenSearch, agente, back_data (mock),
# maintenance, trx_noreconocida (mock) y el front de prueba (Streamlit).
# El error_handler no tiene compose (es fire-and-forget) -> se omite.
#
# Uso:
#   scripts/local_stack.sh up      [--engine docker|podman] [--core]
#   scripts/local_stack.sh down    [--engine docker|podman]
#   scripts/local_stack.sh status  [--engine docker|podman]
#   scripts/local_stack.sh logs <servicio>
#   scripts/local_stack.sh urls
#   scripts/local_stack.sh env     # solo genera .env/overrides, no levanta nada
#
#   --core     : solo OpenSearch + agente + front (suficiente para saludo/clarificación/terceros).
#   --insecure : pre-descarga las imágenes base con --tls-verify=false (podman).
#                Úsalo en la red corporativa de BBVA (TLS interceptado / CA propia).
#
# Notas:
#  - Sin API key => el ruteo cae a FALLBACK y el juez de alcance queda apagado.
#  - macOS: host.docker.internal (Docker) / host.containers.internal (Podman) se
#    resuelven solos. El script usa el alias correcto según el motor.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CMD="${1:-up}"; shift || true
ENGINE=""; CORE=0; LOG_SVC=""; INSECURE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --engine)   ENGINE="${2:-}"; shift 2;;
    --core)     CORE=1; shift;;
    --insecure) INSECURE=1; shift;;
    *)          LOG_SVC="$1"; shift;;
  esac
done

# --- Motor de contenedores ---------------------------------------------------
if [ -z "$ENGINE" ]; then
  if command -v podman >/dev/null 2>&1; then ENGINE="podman"
  elif command -v docker >/dev/null 2>&1; then ENGINE="docker"
  else echo "ERROR: no encuentro docker ni podman en el PATH." >&2; exit 1; fi
fi
COMPOSE="$ENGINE compose"
if [ "$ENGINE" = "podman" ]; then HOST_ALIAS="host.containers.internal"; else HOST_ALIAS="host.docker.internal"; fi

# --- Módulos (nombre | dir | archivo compose | puerto) -----------------------
OS_DIR="co_pqrs_back_opensearch";       OS_FILE="docker-compose.yml"
AG_DIR="co_pqrs_back_agent";            AG_FILE="compose.yml"
DT_DIR="co_pqrs_back_data";             DT_FILE="compose.yml"
MT_DIR="co_pqrs_back_maintenance";      MT_FILE="compose.yaml"
TX_DIR="co_pqrs_back_trx_noreconocida"; TX_FILE="compose.yml"
FR_DIR="co_pqrs_front_test";            FR_FILE="compose.yml"

# Imágenes base necesarias (OpenSearch + base de TODOS los builds de Python).
# Pre-descargarlas resuelve el pull en redes corporativas que interceptan TLS.
BASE_IMAGES=(
  "docker.io/opensearchproject/opensearch:2.9.0"
  "docker.io/opensearchproject/opensearch-dashboards:2.9.0"
  "docker.io/library/python:3.14-slim"
)

prepull_bases() {
  local tls=""
  # --tls-verify=false solo aplica a podman; acepta el cert corporativo (MITM).
  if [ "$ENGINE" = "podman" ] && [ "$INSECURE" -eq 1 ]; then tls="--tls-verify=false"; fi
  echo "== pre-descarga de imágenes base ${tls:+(tls-verify off)} =="
  local img
  for img in "${BASE_IMAGES[@]}"; do
    if $ENGINE pull $tls "$img" >/dev/null 2>&1; then
      echo "  ok: $img"
    else
      echo "  AVISO: falló el pull de $img"
      [ "$INSECURE" -eq 1 ] || echo "        (red corporativa? reintenta con --insecure o instala la CA de BBVA en la VM de podman)"
    fi
  done
}

_w() { # _w <ruta>  (contenido por stdin); no sobrescribe si ya existe
  if [ -f "$1" ]; then echo "  existe (no toco): $1"; cat >/dev/null; else cat > "$1"; echo "  creado: $1"; fi
}

gen_envs() {
  echo "== .env (se crean solo si faltan; motor=$ENGINE alias=$HOST_ALIAS) =="

  _w "$OS_DIR/.env" <<EOF
OPENSEARCH_INITIAL_ADMIN_PASSWORD=Admin_12345!
EOF

  _w "$AG_DIR/.env" <<EOF
# Agente — PRUEBA LOCAL en modo FALLBACK (sin API key del LLM).
BOT_NAME=blue
ENDPOINT=https://local-fallback.invalid/
API_KEY=local-fallback
LLM_MODEL=local-fallback
LLM_EMBEDDINGS=local-fallback
SSL_VERIFY=false
OPENSEARCH_ENDPOINT=https://$HOST_ALIAS:9200
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD=admin
OPENSEARCH_VERIFY_SSL=false
OPENSEARCH_CONVERSATIONS_INDEX=conversations-reference
OPENSEARCH_MESSAGES_INDEX=conversations-messages
OPENSEARCH_TIMEOUT=10
BACK_DATA_SERVICE_URL=http://$HOST_ALIAS:8003
ERROR_HANDLER_SERVICE_URL=http://$HOST_ALIAS:8002
AUDIT_MIN_STATUS=400
END_CONVERSATION_CALLBACK_URL=http://$HOST_ALIAS:8001/end/{conversation_id}
MAX_DAILY_SESSIONS=1000
MAX_DAILY_CATEGORY_INTERACTIONS=1000
MAX_REPEAT_RECHECKS=1000
BACK_DATA_POLL_INTERVAL_SECONDS=0.25
BACK_DATA_MAX_POLL_ATTEMPTS=60
# Juez de alcance APAGADO (usa LLM; sin API key fallaría).
GUARDRAIL_JUDGE_ENABLED=false
REQUEST_LOG_CAPTURE_ENABLED=false
RABBITMQ_ENABLED=false
EOF

  _w "$DT_DIR/.env" <<EOF
# back_data — MOCK (sin Postgres ni ASO reales).
COMPONENT_VERSION=1.0.0
API_V0_STR=/pqrs/v0
DATA_CSV=unifi
CUSTOMER_IDENTITY_SOURCE=mock
COMMERCIAL_INFO_SOURCE=mock
COMMERCIAL_INFO_MOCK_DIR=data
COMMERCIAL_INFO_FILE_PREFIX=commercial_info_
SSL_VERIFY=false
OPENSEARCH_ENDPOINT=https://$HOST_ALIAS:9200
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD=admin
OPENSEARCH_VERIFY_SSL=false
OPENSEARCH_CONVERSATIONS_INDEX=conversations-reference
OPENSEARCH_MESSAGES_INDEX=conversations-messages
OPENSEARCH_CONTROL_INDEX=client-control-table
OPENSEARCH_TIMEOUT=10
AUDIT_MIN_STATUS=400
MAIL_ENABLED=false
CORS_ALLOW_ORIGINS=*
CORS_ALLOW_METHODS=*
CORS_ALLOW_HEADERS=*
EOF

  _w "$MT_DIR/.env" <<EOF
# maintenance — barrido de conversaciones inactivas.
OPENSEARCH_ENDPOINT=https://$HOST_ALIAS:9200
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD=admin
OPENSEARCH_VERIFY_SSL=false
OPENSEARCH_CONVERSATIONS_INDEX=conversations-reference
OPENSEARCH_MESSAGES_INDEX=conversations-messages
OPENSEARCH_TIMEOUT=10
INACTIVE_MINUTES=5
EOF
}

gen_overrides() {
  # El compose del agente hardcodea OPENSEARCH_ENDPOINT a host.containers.internal;
  # lo forzamos al alias del motor elegido (clave para Docker en macOS).
  cat > "$AG_DIR/compose.local.yml" <<EOF
services:
  co-pqrs-back-agent:
    environment:
      OPENSEARCH_ENDPOINT: https://$HOST_ALIAS:9200
EOF
  # El front (Streamlit) llama al agente desde el contenedor -> host alias.
  cat > "$FR_DIR/compose.local.yml" <<EOF
services:
  co_pqrs_front_test:
    environment:
      PQRS_AGENT_API_URL: http://$HOST_ALIAS:8000
EOF
  # OpenSearch: volúmenes NOMBRADOS (perms correctos) en vez del bind-mount
  # ./opensearch/data, que en la VM de podman/Docker en macOS provoca
  # AccessDeniedException y hace que OpenSearch no arranque (context_storage_error).
  cat > "$OS_DIR/docker-compose.local.yml" <<EOF
services:
  opensearch-node1:
    volumes:
      - osdata1:/usr/share/opensearch/data
  opensearch-node2:
    volumes:
      - osdata2:/usr/share/opensearch/data
volumes:
  osdata1:
  osdata2:
EOF
  echo "  overrides: $AG_DIR/compose.local.yml, $FR_DIR/compose.local.yml, $OS_DIR/docker-compose.local.yml"
}

_up() { # _up <nombre> <dir> <file> [args extra de compose]
  local name="$1" dir="$2" file="$3"; shift 3
  echo "== up: $name =="
  ( cd "$dir" && $COMPOSE -f "$file" "$@" up --build -d )
}
_down() { local dir="$1" file="$2"; shift 2; ( cd "$dir" && $COMPOSE -f "$file" "$@" down 2>/dev/null || true ); }

wait_opensearch() {
  echo "== esperando OpenSearch en https://localhost:9200 (hasta ~3 min) =="
  for _ in $(seq 1 60); do
    if curl -sk -u admin:admin https://localhost:9200 >/dev/null 2>&1; then echo "  OpenSearch OK"; return 0; fi
    sleep 3
  done
  echo "  AVISO: OpenSearch no respondió; el agente/back_data podrían fallar al persistir."
}

cmd_urls() {
  cat <<EOF

===================== URLs =====================
  Agente API .......... http://localhost:8000   (/health, /docs, /start, /chat)
  Front de prueba ..... http://localhost:8501
  back_data ........... http://localhost:8003/docs
  trx_noreconocida .... http://localhost:8004/docs
  maintenance ......... http://localhost:8001
  OpenSearch .......... https://localhost:9200   (admin/admin)
  OpenSearch Dashboards http://localhost:5601
================================================
Probar por CLI:
  curl -s http://localhost:8000/start -H 'Content-Type: application/json' -d '{"user_id":"03966512"}'
EOF
}

cmd_up() {
  gen_envs; gen_overrides
  prepull_bases
  _up OpenSearch "$OS_DIR" "$OS_FILE" -f docker-compose.local.yml
  wait_opensearch
  if [ "$CORE" -eq 0 ]; then
    _up back_data        "$DT_DIR" "$DT_FILE"
    _up trx_noreconocida "$TX_DIR" "$TX_FILE"
    _up maintenance      "$MT_DIR" "$MT_FILE"
  fi
  _up agente "$AG_DIR" "$AG_FILE" -f compose.local.yml
  _up front  "$FR_DIR" "$FR_FILE" -f compose.local.yml
  echo; echo "Stack arriba (motor=$ENGINE). Puede tardar en compilar la primera vez."
  cmd_urls
}

cmd_hybrid() {
  # Modo HÍBRIDO (recomendado en Podman/macOS): OpenSearch + back_trx en
  # contenedor (puertos publicados) y el AGENTE en el HOST con uv, que sí alcanza
  # localhost:9200 y localhost:8004 (los contenedores entre sí no se alcanzan de
  # forma fiable en podman-machine).
  if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: 'uv' no está instalado (se necesita para correr el agente en el host)." >&2
    exit 1
  fi
  gen_envs; gen_overrides; prepull_bases
  _up OpenSearch "$OS_DIR" "$OS_FILE" -f docker-compose.local.yml
  wait_opensearch
  _up trx_noreconocida "$TX_DIR" "$TX_FILE"

  # .env del agente para correr en el HOST (endpoints a localhost).
  cat > "$AG_DIR/.env" <<EOF
BOT_NAME=blue
ENDPOINT=https://local-fallback.invalid/
API_KEY=local-fallback
LLM_MODEL=local-fallback
LLM_EMBEDDINGS=local-fallback
SSL_VERIFY=false
OPENSEARCH_ENDPOINT=https://localhost:9200
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD=admin
OPENSEARCH_VERIFY_SSL=false
OPENSEARCH_CONVERSATIONS_INDEX=conversations-reference
OPENSEARCH_MESSAGES_INDEX=conversations-messages
OPENSEARCH_TIMEOUT=10
TRX_SERVICE_URL=http://localhost:8004
BACK_DATA_SERVICE_URL=
ERROR_HANDLER_SERVICE_URL=
AUDIT_MIN_STATUS=400
END_CONVERSATION_CALLBACK_URL=http://localhost:8001/end/{conversation_id}
MAX_DAILY_SESSIONS=1000
MAX_DAILY_CATEGORY_INTERACTIONS=1000
MAX_REPEAT_RECHECKS=1000
BACK_DATA_POLL_INTERVAL_SECONDS=0.25
BACK_DATA_MAX_POLL_ATTEMPTS=60
GUARDRAIL_JUDGE_ENABLED=false
REQUEST_LOG_CAPTURE_ENABLED=false
RABBITMQ_ENABLED=false
EOF

  cat <<EOF

============ MODO HÍBRIDO ============
  Contenedores arriba: OpenSearch (:9200) + back_trx (:8004)
  Ahora corre el AGENTE en el HOST (Ctrl+C para parar; los contenedores siguen).
  Front (en otra terminal, en el host):
    cd co_pqrs_front_test && PQRS_AGENT_API_URL=http://localhost:8000 uv run streamlit run main.py
  Probar: http://localhost:8000/docs  |  front: http://localhost:8501
=====================================
EOF
  ( cd "$AG_DIR" && exec uv run uvicorn --app-dir src \
      infrastructure.entrypoint.fastapi_app:app --host 0.0.0.0 --port 8000 --reload )
}


cmd_down() {
  _down "$FR_DIR" "$FR_FILE" -f compose.local.yml
  _down "$AG_DIR" "$AG_FILE" -f compose.local.yml
  _down "$MT_DIR" "$MT_FILE"
  _down "$TX_DIR" "$TX_FILE"
  _down "$DT_DIR" "$DT_FILE"
  _down "$OS_DIR" "$OS_FILE" -f docker-compose.local.yml
  echo "Stack detenido."
}

cmd_status() { $ENGINE ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || $ENGINE ps; }

cmd_logs() {
  [ -n "$LOG_SVC" ] || { echo "Uso: local_stack.sh logs <nombre-contenedor>"; exit 1; }
  $ENGINE logs -f "$LOG_SVC"
}

case "$CMD" in
  up)     cmd_up;;
  hybrid) cmd_hybrid;;
  down)   cmd_down;;
  status) cmd_status;;
  logs)   cmd_logs;;
  urls)   cmd_urls;;
  env)    gen_envs; gen_overrides; echo "Listo (solo .env/overrides).";;
  *) echo "Uso: $0 {up|hybrid|down|status|logs <svc>|urls|env} [--engine docker|podman] [--core] [--insecure]"; exit 1;;
esac
