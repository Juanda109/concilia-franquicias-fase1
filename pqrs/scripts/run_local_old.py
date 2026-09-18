#!/usr/bin/env python3
"""
Lanzador local cross-platform (macOS / Windows / Linux) del stack PQRs en modo
HÍBRIDO: OpenSearch + back_trx en contenedor (podman/docker) y el AGENTE + FRONT
en el HOST (con uv), porque en podman-machine los contenedores no se alcanzan
entre sí de forma fiable pero el host SÍ alcanza los puertos publicados.

Un solo comando:  python scripts/run_local_old.py            (levanta todo)
                  python scripts/run_local_old.py down       (baja los contenedores)

Abre automáticamente 2 terminales nuevas (agente y front). Requiere: podman
(o docker) y uv instalados. Solo usa librería estándar.

Opciones:
  --engine podman|docker   (por defecto: autodetecta, prefiere podman)
  --insecure               (pre-pull con --tls-verify=false; red corporativa BBVA)
  --no-spawn               (no abre terminales; imprime los comandos del host)
"""
from __future__ import annotations

import argparse
import base64
import os
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"

OS_DIR = ROOT / "co_pqrs_back_opensearch"
AG_DIR = ROOT / "co_pqrs_back_agent"
TX_DIR = ROOT / "co_pqrs_back_trx_noreconocida"
FR_DIR = ROOT / "co_pqrs_front_test"
DC_DIR = ROOT / "co_pqrs_back_doble_cobro"
AS_DIR = ROOT / "co_pqrs_back_trx_aso_simulator"

OS_LOCAL = "os-local.yml"

BASE_IMAGES = (
    "docker.io/opensearchproject/opensearch:2.9.0",
    "docker.io/opensearchproject/opensearch-dashboards:2.9.0",
    "docker.io/library/python:3.14-slim",
)

# --- Contenido de .env / overrides (autogenerado, idempotente) ---------------
# OpenSearch de UN SOLO nodo (estable con poca memoria en la VM de podman),
# volumen nombrado (perms correctos) y puerto 9200 publicado.
OS_LOCAL_YML = """\
services:
  opensearch:
    image: opensearchproject/opensearch:2.9.0
    container_name: opensearch-node1
    environment:
      - discovery.type=single-node
      - bootstrap.memory_lock=true
      - OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m
      - OPENSEARCH_INITIAL_ADMIN_PASSWORD=Admin_12345!
    ulimits:
      memlock:
        soft: -1
        hard: -1
      nofile:
        soft: 65536
        hard: 65536
    ports:
      - "9200:9200"
    volumes:
      - osdata1:/usr/share/opensearch/data

  opensearch-dashboards:
    image: opensearchproject/opensearch-dashboards:2.9.0
    container_name: opensearch-dashboards
    ports:
      - "5601:5601"
    environment:
      - 'OPENSEARCH_HOSTS=["https://opensearch:9200"]'
      - OPENSEARCH_USERNAME=admin
      - OPENSEARCH_PASSWORD=admin
    depends_on:
      - opensearch

volumes:
  osdata1:
"""

AGENT_ENV = """\
# Agente en el HOST (modo híbrido): endpoints a localhost.
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
# Interruptor del flujo TXNR. Por defecto es false y desvia TODO el flujo
# al formulario PQR (paso 2.4.0.4.pqr).
TRX_FLOW_ENABLED=true
# Recurrencia-bot: por defecto 1, asi que a la SEGUNDA prueba con el mismo
# cliente el bot desvia al formulario. Se sube para poder repetir pruebas.
MAX_TRX_BOT_RECURRENCE=1000
DC_SERVICE_URL=http://localhost:8006
TRANSACTIONS_PER_PAGE=6
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
"""

# El servicio de doble cobro consulta el simulador ASO del host (:8050).
DOBLE_COBRO_ENV = """\
DOBLE_COBRO_LOG_LEVEL=INFO
DC_ASO_BASE_URL=http://127.0.0.1:8050
DC_ASO_FO_PATH=/financial-overview/v0/financial-overview
DC_ASO_OPERATIONS_PATH=/cards/v2/operations
DC_SETTLEMENT_DAYS=7
DC_MAX_REPORT_MONTHS=6
DC_VISA_VALIDITY_DAYS=180
DC_MASTER_VALIDITY_DAYS=120
DC_AMOUNT_TOLERANCE=2000
"""

AGENT_CMD = (
    "{uv} run uvicorn --app-dir src "
    "infrastructure.entrypoint.fastapi_app:app --host 0.0.0.0 --port 8000 --reload"
)
FRONT_CMD = "{uv} run streamlit run main.py --server.port 8501 --server.address 0.0.0.0"
DOBLE_COBRO_CMD = (
    "{uv} run uvicorn --app-dir src "
    "infrastructure.entrypoint.fastapi_app:app --host 127.0.0.1 --port 8006 --reload"
)
ASO_SIM_CMD = (
    "{uv} run uvicorn --app-dir src "
    "infrastructure.entrypoint.fastapi_app:app --host 127.0.0.1 --port 8050 --reload"
)


def sh(args, cwd=None, check=True):
    print("+", " ".join(str(a) for a in args))
    return subprocess.run([str(a) for a in args], cwd=str(cwd) if cwd else None, check=check)


def detect_engine(pref: str | None) -> str:
    candidates = ([pref] if pref else []) + ["podman", "docker"]
    for engine in candidates:
        if engine and shutil.which(engine):
            return engine
    sys.exit("ERROR: no encontré 'podman' ni 'docker' en el PATH.")


def compose(engine: str) -> list[str]:
    return [engine, "compose"]


def write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    print("  archivo:", path.relative_to(ROOT))


def prepull(engine: str, insecure: bool) -> None:
    print("== pre-descarga de imágenes base ==")
    # En podman usamos --tls-verify=false por defecto (redes corporativas con CA propia).
    tls = ["--tls-verify=false"] if engine == "podman" else []
    for img in BASE_IMAGES:
        subprocess.run([engine, "pull", *tls, img], check=False)


def wait_opensearch(timeout_s: int = 240) -> bool:
    print("== esperando OpenSearch en https://localhost:9200 ==")
    ctx = ssl._create_unverified_context()
    auth = base64.b64encode(b"admin:admin").decode()
    req = urllib.request.Request(
        "https://localhost:9200/_cluster/health",
        headers={"Authorization": "Basic " + auth},
    )
    for _ in range(max(1, timeout_s // 3)):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
                if resp.status == 200:
                    print("  OpenSearch OK")
                    return True
        except urllib.error.HTTPError:
            # El servidor responde (p.ej. 503 inicializando seguridad) -> está arriba.
            print("  OpenSearch respondiendo (inicializando seguridad)")
            time.sleep(6)
            return True
        except Exception:
            pass
        time.sleep(3)
    print("  AVISO: OpenSearch no respondió; verifica: curl -sk -u admin:admin https://localhost:9200/_cluster/health")
    return False


def open_terminal(title: str, command: str, cwd: Path) -> None:
    """Abre una terminal nueva que corre `command` en `cwd` (por SO).

    Redirige el Python/caché de uv a $HOME/.uv para evitar 'Permission denied'
    en ~/.local/share/uv. Sin comillas dobles (rompen el osascript de macOS).
    """
    cwd_s = str(cwd)
    if not IS_WIN:
        uv_env = (
            "export UV_PYTHON_INSTALL_DIR=$HOME/.uv/python UV_CACHE_DIR=$HOME/.uv/cache "
            "UV_NATIVE_TLS=1; "
            "mkdir -p $HOME/.uv/python $HOME/.uv/cache; "
        )
        full = f"cd {cwd_s} && {uv_env}{command}"
        if IS_MAC:
            osa = f'tell application "Terminal" to do script "{full}"'
            subprocess.Popen(["osascript", "-e", osa])
            return
        for term in (
            ["gnome-terminal", f"--title={title}", "--", "bash", "-lc", f"{full}; exec bash"],
            ["x-terminal-emulator", "-e", f"bash -lc \"{full}; exec bash\""],
            ["xterm", "-T", title, "-e", f"bash -lc \"{full}; exec bash\""],
        ):
            if shutil.which(term[0]):
                subprocess.Popen(term)
                return
        print(f"  (No pude abrir terminal) Corre manualmente en {cwd_s}:\n    {command}")
    else:
        win_env = (
            "set UV_PYTHON_INSTALL_DIR=%USERPROFILE%\\.uv\\python&& "
            "set UV_CACHE_DIR=%USERPROFILE%\\.uv\\cache&& "
            "set UV_NATIVE_TLS=1&& "
        )
        subprocess.Popen(
            f'start "{title}" cmd /k "cd /d {cwd_s}&& {win_env}{command}"', shell=True
        )


def cmd_up(engine: str, insecure: bool, spawn: bool) -> None:
    uv_bin = shutil.which("uv")
    if not uv_bin:
        sys.exit("ERROR: 'uv' no está instalado (necesario para el agente/front en el host).")
    agent_cmd = AGENT_CMD.format(uv=uv_bin)
    front_cmd = FRONT_CMD.format(uv=uv_bin)
    doble_cobro_cmd = DOBLE_COBRO_CMD.format(uv=uv_bin)
    aso_sim_cmd = ASO_SIM_CMD.format(uv=uv_bin)

    print(f"== motor: {engine} | SO: {'windows' if IS_WIN else 'macos' if IS_MAC else 'linux'} ==")
    write(OS_DIR / OS_LOCAL, OS_LOCAL_YML)
    if not (AG_DIR / ".env").exists():
        write(AG_DIR / ".env", AGENT_ENV)
    if not (DC_DIR / ".env").exists():
        write(DC_DIR / ".env", DOBLE_COBRO_ENV)

    if insecure or engine == "podman":
        prepull(engine, insecure)

    print("== up OpenSearch (contenedor) ==")
    sh(compose(engine) + ["-f", OS_LOCAL, "up", "-d"], cwd=OS_DIR)
    wait_opensearch()

    print("== up back_trx (contenedor) ==")
    sh(compose(engine) + ["-f", "compose.yml", "up", "--build", "-d"], cwd=TX_DIR)

    print("\n== HOST: simulador ASO + doble cobro + agente + front ==")
    if spawn:
        # El simulador ASO va primero: doble cobro lo consulta en cuanto
        # el flujo pide productos o movimientos.
        open_terminal("PQRs-aso-sim", aso_sim_cmd, AS_DIR)
        open_terminal("PQRs-doble-cobro", doble_cobro_cmd, DC_DIR)
        open_terminal("PQRs-agente", agent_cmd, AG_DIR)
        open_terminal("PQRs-front", front_cmd, FR_DIR)
        print(
            "  Se abrieron 4 terminales "
            "(ASO sim :8050, doble cobro :8006, agente :8000, front :8501)."
        )
    else:
        print(f"  ASO sim      ->  (cd {AS_DIR})  {aso_sim_cmd}")
        print(f"  Doble cobro  ->  (cd {DC_DIR})  {doble_cobro_cmd}")
        print(f"  Agente       ->  (cd {AG_DIR})  {agent_cmd}")
        print(f"  Front        ->  (cd {FR_DIR})  {front_cmd}")

    print(
        "\n===================== LISTO =====================\n"
        "  Agente API .......... http://localhost:8000/docs\n"
        "  Front (Streamlit) ... http://localhost:8501\n"
        "  OpenSearch .......... https://localhost:9200 (admin/admin)\n"
        "  back_trx ............ http://localhost:8004/docs\n"
        "  Doble cobro ......... http://localhost:8006/docs\n"
        "  Simulador ASO ....... http://localhost:8050/docs\n"
        "  Prueba TXNR .......... user_id=13083558 -> 'compra presencial o por internet'\n"
"                        -> Visa Debito *4818 -> $35.000-$500.000 -> 20/08/2026\n"
"  Prueba doble cobro ... user_id=13083558 -> cuenta de ahorro -> Ahorro Libreton *2384\n"
"                        -> 20/08/2026 -> monto 145000\n"
        "  Parar: cierra las terminales del agente/front y corre:\n"
        "         python scripts/run_local_old.py down\n"
        "================================================="
    )


def cmd_down(engine: str) -> None:
    print("== down back_trx ==")
    sh(compose(engine) + ["-f", "compose.yml", "down"], cwd=TX_DIR, check=False)
    print("== down OpenSearch ==")
    sh(compose(engine) + ["-f", OS_LOCAL, "down"], cwd=OS_DIR, check=False)
    print("Contenedores detenidos (cierra las terminales del agente/front si siguen abiertas).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Lanzador local híbrido cross-platform")
    parser.add_argument("command", nargs="?", default="up", choices=["up", "down"])
    parser.add_argument("--engine", choices=["podman", "docker"], default=None)
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--no-spawn", action="store_true")
    args = parser.parse_args()

    engine = detect_engine(args.engine)
    if args.command == "down":
        cmd_down(engine)
    else:
        cmd_up(engine, insecure=args.insecure, spawn=not args.no_spawn)


if __name__ == "__main__":
    main()
