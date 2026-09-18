#!/usr/bin/env python3
"""Host-only launcher for priority PQRs services (no Docker/Podman).

Starts/stops these services on the host using ``uv``:
 - co_pqrs_back_agent                :8000
 - co_pqrs_back_data                 :8003
 - co_pqrs_back_trx_noreconocida     :8004
 - co_pqrs_back_trx_aso_simulator    :8050
 - co_pqrs_authorization             :8005
 - co_pqrs_front_test                :8501

Usage:
  python scripts/run_local.py up
  python scripts/run_local.py down
  python scripts/run_local.py status

Optional:
    --sync         Force dependency install/sync in each service.
    --use-postgres Use local PostgreSQL for TXNR products.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "scripts" / ".local_run"
PID_DIR = STATE_DIR / "pids"
LOG_DIR = STATE_DIR / "logs"
IS_WIN = os.name == "nt"


@dataclass(frozen=True)
class Service:
    name: str
    directory: Path
    command: list[str]
    env_content: str | None = None


SERVICES = (
    Service(
        name="doble_cobro",
        directory=ROOT / "co_pqrs_back_doble_cobro",
        command=[
            "uv",
            "run",
            "uvicorn",
            "--app-dir",
            "src",
            "infrastructure.entrypoint.fastapi_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8006",
        ],
        env_content=(
            "DOBLE_COBRO_SERVICE_PORT=8006\n"
            "DOBLE_COBRO_LOG_LEVEL=INFO\n"

            # ASO local
            "DC_ASO_BASE_URL=http://127.0.0.1:8050\n"

            # GrantingTicket
            "DC_ASO_TICKET_URL=\n"
            "DC_ASO_API_USER_ID=ZM12035\n"
            "DC_ASO_API_CONSUMER_ID=12000035\n"
            "DC_ASO_API_AUTHENTICATION_TYPE=04\n"
            "DC_ASO_API_PASSWORD=PTDada2026_PQRS\n"
            "DC_ASO_API_VERIFY_SSL=false\n"
            "DC_ASO_API_TIMEOUT=30\n"

            # Endpoints ASO
            "DC_ASO_FO_PATH=/financial-overview/v0/financial-overview\n"
            "DC_ASO_OPERATIONS_PATH=/cards/v2/operations\n"

            # Reglas de negocio
            "DC_SETTLEMENT_DAYS=7\n"
            "DC_MAX_REPORT_MONTHS=6\n"
            "DC_VISA_VALIDITY_DAYS=180\n"
            "DC_MASTER_VALIDITY_DAYS=120\n"
            "DC_AMOUNT_TOLERANCE=2000\n"
        ),
    ),
    Service(
        name="trx_aso_simulator",
        directory=ROOT / "co_pqrs_back_trx_aso_simulator",
        command=[
            "uv",
            "run",
            "uvicorn",
            "--app-dir",
            "src",
            "infrastructure.entrypoint.fastapi_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8050",
        ],
        env_content=(
            "LOCAL_CONTINGENCY_MODE=true\n"
        ),
    ),
    Service(
        name="trx_noreconocida",
        directory=ROOT / "co_pqrs_back_trx_noreconocida",
        command=[
            "uv",
            "run",
            "uvicorn",
            "--app-dir",
            "src",
            "infrastructure.entrypoint.fastapi_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8004",
        ],
        env_content=(
            "TRX_SERVICE_PORT=8004\n"
            "TRX_LOG_LEVEL=INFO\n"
            "LOCAL_CONTINGENCY_MODE=true\n"
            # Productos: mock hardcodeado (sin FO).
            # Las tarjetas del mock apuntan al cliente 1010223694,
            # que SI tiene fixture en el simulador.
            # Usar user_id=1010223694 en POST /start.
            "TRX_PRODUCTS_SOURCE=mock\n"
            "TRX_ALLOW_MOCKS=true\n"
            "TRX_SALESFORCE_SOURCE=mock\n"
            "TRX_SALESFORCE_MOCK_FILE=data/aso_salesforce_no_recurrence.json\n"
            "TRX_MOVEMENTS_SOURCE=mock\n"
            # ASO: simulador local. NUNCA apunta al ASO real de BBVA.
            "ASO_SOURCE=simulator\n"
            "ASO_SIMULATOR_URL=http://127.0.0.1:8050\n"
            "ASO_REAL_URL=\n"
            "ASO_BASE_URL=\n"
            "TRX_TICKET_URL=\n"
            "TRX_API_VERIFY_SSL=false\n"
            "ERROR_HANDLER_SERVICE_URL=\n"
            "DIAS_HABILES_DEVOLUCION=40\n"
            "DIAS_HABILES_TARJETA=5\n"
        ),
    ),
    Service(
        name="back_data",
        directory=ROOT / "co_pqrs_back_data",
        command=[
            "uv",
            "run",
            "uvicorn",
            "--app-dir",
            "src",
            "infrastructure.entrypoint.fastapi_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8003",
        ],
        env_content=(
            "CUSTOMER_IDENTITY_SOURCE=mock\n"
            # LOCAL_IDENTITY_CSV=identidad_grounding hace que el saludo de /start
            # tenga nombres de pila que comprobar (dataset de grounding).
            f"DATA_CSV={os.getenv('LOCAL_IDENTITY_CSV', 'unifi')}\n"
            "COMMERCIAL_INFO_SOURCE=mock\n"
            "COMMERCIAL_INFO_MOCK_DIR=data\n"
            "COMMERCIAL_INFO_FILE_PREFIX=commercial_info_\n"
            "OPENSEARCH_ENABLED=false\n"
            "AUDIT_MIN_STATUS=400\n"
        ),
    ),
    Service(
        name="authorization",
        directory=ROOT / "co_pqrs_authorization",
        command=[
            "uv",
            "run",
            "uvicorn",
            "--app-dir",
            "src",
            "infrastructure.entrypoint.fastapi_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8005",
        ],
        env_content=(
            "AUTHORIZATION_SERVICE_PORT=8005\n"
            "AUTHORIZATION_DEADLINE_SECONDS=180\n"
            # worker rapido en local para ver el ciclo enseguida
            "AUTHORIZATION_WORKER_ENABLED=true\n"
            "AUTHORIZATION_WORKER_TICK=2\n"
            "AUTHORIZATION_RETRY_SECONDS=3\n"
            "AUTHORIZATION_LEASE_SECONDS=30\n"
            "AUTHORIZATION_WORKER_BATCH=20\n"
            # persistencia: OpenSearch local (el servicio crea el indice al arrancar)
            "OPENSEARCH_URL=https://localhost:9200\n"
            "OPENSEARCH_USER=admin\n"
            "OPENSEARCH_PASS=admin\n"
            "AUTHORIZATIONS_INDEX=authorizations\n"
            "ERROR_HANDLER_SERVICE_URL=\n"
            "OPENSEARCH_VERIFY_SSL=false\n"
            # ASO: SOLO el simulador local, NUNCA el ASO real de BBVA
            "ASO_SOURCE=simulator\n"
            "ASO_SIMULATOR_URL=http://127.0.0.1:8050\n"
            "TRX_API_CONSUMER_ID=12000035\n"
            "TRX_API_AUTHENTICATION_TYPE=04\n"
        ),
    ),
    Service(
        name="agent",
        directory=ROOT / "co_pqrs_back_agent",
        command=[
            "uv",
            "run",
            "uvicorn",
            "--app-dir",
            "src",
            "infrastructure.entrypoint.fastapi_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        env_content=(
            "BOT_NAME=blue\n"
            "LOCAL_CONTINGENCY_MODE=true\n"
            "ENDPOINT=https://local-fallback.invalid/\n"
            "API_KEY=local-fallback\n"
            "LLM_MODEL=local-fallback\n"
            "LLM_EMBEDDINGS=local-fallback\n"
            "SSL_VERIFY=false\n"
            "OPENSEARCH_ENABLED=false\n"
            "OPENSEARCH_ENDPOINT=https://localhost:9200\n"
            "OPENSEARCH_USER=admin\n"
            "OPENSEARCH_PASSWORD=admin\n"
            "OPENSEARCH_VERIFY_SSL=false\n"
            "OPENSEARCH_CONVERSATIONS_INDEX=conversations-reference\n"
            "OPENSEARCH_MESSAGES_INDEX=conversations-messages\n"
            "OPENSEARCH_TIMEOUT=10\n"
            "BACK_DATA_SERVICE_URL=http://127.0.0.1:8003\n"
            "TRX_SERVICE_URL=http://127.0.0.1:8004\n"
            "TRX_FLOW_ENABLED=true\n"
            "DC_SERVICE_URL=http://127.0.0.1:8006\n"
            "TRANSACTIONS_PER_PAGE=6\n"
            "ERROR_HANDLER_SERVICE_URL=\n"
            "AUDIT_MIN_STATUS=400\n"
            "END_CONVERSATION_CALLBACK_URL="
            "http://127.0.0.1:8001/end/{conversation_id}\n"
            "MAX_DAILY_SESSIONS=1000\n"
            "MAX_DAILY_CATEGORY_INTERACTIONS=1000\n"
            "MAX_REPEAT_RECHECKS=1000\n"
            "MAX_TRX_BOT_RECURRENCE=1000\n"
            "DIAS_HABILES_DEVOLUCION=40\n"
            "DIAS_HABILES_TARJETA=10\n"
            "BACK_DATA_POLL_INTERVAL_SECONDS=0.25\n"
            "BACK_DATA_MAX_POLL_ATTEMPTS=60\n"
            "GUARDRAIL_JUDGE_ENABLED=false\n"
            "REQUEST_LOG_CAPTURE_ENABLED=false\n"
            "RABBITMQ_ENABLED=false\n"
        ),
    ),
    Service(
        name="front_test",
        directory=ROOT / "co_pqrs_front_test",
        command=[
            "uv",
            "run",
            "streamlit",
            "run",
            "main.py",
            "--server.port",
            "8501",
            "--server.address",
            "127.0.0.1",
        ],
        env_content=(
            "PQRS_AGENT_API_URL=http://127.0.0.1:8000\n"
        ),
    ),
)


def resolve_runner() -> tuple[str, str]:
    """Resolve dependency/runtime launcher.

    Returns:
        tuple(kind, executable)
        - kind=uv     -> executable is uv binary path.
        - kind=python -> executable is base Python used to create venvs.
    """

    uv_bin = shutil.which("uv")
    if uv_bin:
        return "uv", uv_bin

    if IS_WIN:
        local_python = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        local_python = ROOT / ".venv" / "bin" / "python"

    if local_python.exists():
        return "python", str(local_python)

    return "python", sys.executable


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _with_local_rabbitmq(env_content: str) -> str:
    """Agente publicando al RabbitMQ local (docker-compose.analytics.yml).

    Se activa con LOCAL_RABBITMQ_ENABLED=true al hacer `up`: los eventos
    conversation.* salen por el exchange pqr.events y Logstash los indexa en
    el OpenSearch local, igual que en OKD.
    """

    env_map: dict[str, str] = {}
    for raw_line in env_content.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_map[key] = value
    env_map.update(
        {
            "RABBITMQ_ENABLED": "true",
            "RABBITMQ_HOST": os.getenv("LOCAL_RABBITMQ_HOST", "127.0.0.1").strip(),
            "RABBITMQ_PORT": os.getenv("LOCAL_RABBITMQ_PORT", "5672").strip(),
            "RABBITMQ_VHOST": "/",
            "RABBITMQ_USER": os.getenv("LOCAL_RABBITMQ_USER", "guest").strip(),
            "RABBITMQ_PASSWORD": os.getenv("LOCAL_RABBITMQ_PASSWORD", "guest").strip(),
            "RABBITMQ_EXCHANGE": "pqr.events",
            "RABBITMQ_EXCHANGE_TYPE": "topic",
        }
    )
    return "\n".join(f"{k}={v}" for k, v in env_map.items()) + "\n"


def _with_real_llm(env_content: str) -> str:
    """Agente con el LLM REAL en vez del fallback de contingencia.

    Se activa con LOCAL_LLM_REAL=true al hacer `up` y toma las credenciales de
    las variables LOCAL_LLM_ENDPOINT, LOCAL_LLM_API_KEY, LOCAL_LLM_MODEL y
    LOCAL_LLM_EMBEDDINGS del entorno del shell (nunca del repo). Es lo que se
    necesita para correr el benchmark, el canario o los datasets adversariales
    contra el router de verdad; en contingencia solo se mide el fallback.
    """

    endpoint = os.getenv("LOCAL_LLM_ENDPOINT", "").strip()
    api_key = os.getenv("LOCAL_LLM_API_KEY", "").strip()
    if not endpoint or not api_key:
        raise SystemExit(
            "LOCAL_LLM_REAL=true exige LOCAL_LLM_ENDPOINT y LOCAL_LLM_API_KEY en el entorno "
            "(y opcionalmente LOCAL_LLM_MODEL / LOCAL_LLM_EMBEDDINGS)."
        )
    env_map: dict[str, str] = {}
    for raw_line in env_content.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_map[key] = value
    env_map.update(
        {
            "LOCAL_CONTINGENCY_MODE": "false",
            "ENDPOINT": endpoint,
            "API_KEY": api_key,
            "LLM_MODEL": os.getenv("LOCAL_LLM_MODEL", "agentepqrs-llm-live-agent-gpt54mini").strip(),
            "LLM_EMBEDDINGS": os.getenv(
                "LOCAL_LLM_EMBEDDINGS", "agentepqrs-llm-live-emebed-3-large"
            ).strip(),
        }
    )
    return "\n".join(f"{k}={v}" for k, v in env_map.items()) + "\n"


def _build_env_content(service: Service, use_postgres: bool) -> str | None:
    if service.env_content is None:
        return None

    if service.name == "agent":
        content = service.env_content
        if _env_flag("LOCAL_LLM_REAL"):
            content = _with_real_llm(content)
        if _env_flag("LOCAL_RABBITMQ_ENABLED"):
            content = _with_local_rabbitmq(content)
        if content is not service.env_content:
            return content

    if not use_postgres or service.name != "trx_noreconocida":
        return service.env_content

    # Local realism mode: enable postgres source while preserving
    # safe defaults.
    env_map: dict[str, str] = {}
    for raw_line in service.env_content.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_map[key] = value

    env_map["TRX_PRODUCTS_SOURCE"] = "postgres"
    env_map["DB_HOST"] = os.getenv("LOCAL_PG_HOST", "127.0.0.1").strip()
    env_map["DB_PORT"] = os.getenv("LOCAL_PG_PORT", "5432").strip()
    env_map["DB_NAME"] = os.getenv("LOCAL_PG_DB", "pqr_db").strip()
    env_map["DB_USER"] = os.getenv("LOCAL_PG_USER", "pqr_user").strip()
    env_map["DB_PASS"] = os.getenv("LOCAL_PG_PASS", "pqr_password").strip()
    env_map["TRX_POSTGRES_TABLE"] = os.getenv(
        "LOCAL_PG_TABLE", "ada_info_detail"
    ).strip()

    return "\n".join(f"{k}={v}" for k, v in env_map.items()) + "\n"


def write_env_file(service: Service, use_postgres: bool) -> None:
    env_content = _build_env_content(service, use_postgres)
    if env_content is None:
        return
    env_path = service.directory / ".env"
    env_path.write_text(env_content, encoding="utf-8")
    print(f"  env listo: {env_path.relative_to(ROOT)}")


def run_sync(command: list[str], cwd: Path) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=str(cwd), check=True)


def install_service_deps(service: Service, kind: str, executable: str) -> None:
    """Install dependencies for a service using uv or pip editable install."""

    if kind == "uv":
        run_sync([executable, "sync"], cwd=service.directory)
        return

    run_sync(
        [executable, "-m", "pip", "install", "-e", "."],
        cwd=service.directory,
    )


def resolve_service_command(
    service: Service,
    kind: str,
    executable: str,
) -> list[str]:
    """Build the runtime command for a service."""

    if kind == "uv":
        return service.command

    # Expected uv command shape: uv run <cmd> <args...>
    if len(service.command) < 3 or service.command[0:2] != ["uv", "run"]:
        raise RuntimeError(
            f"Comando inválido para servicio {service.name}: {service.command}"
        )

    runtime_cmd = service.command[2:]
    return [executable, "-m", *runtime_cmd]


def service_pid_path(service: Service) -> Path:
    return PID_DIR / f"{service.name}.pid"


def service_log_path(service: Service) -> Path:
    return LOG_DIR / f"{service.name}.log"


def read_pid(service: Service) -> int | None:
    pid_file = service_pid_path(service)
    if not pid_file.exists():
        return None
    raw = pid_file.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if IS_WIN:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def start_service(service: Service, kind: str, executable: str) -> None:
    current_pid = read_pid(service)
    if current_pid and is_running(current_pid):
        print(f"  {service.name}: ya está corriendo (pid={current_pid})")
        return

    log_path = service_log_path(service)
    with log_path.open("a", encoding="utf-8") as log_file:
        kwargs: dict[str, object] = {
            "cwd": str(service.directory),
            "stdout": log_file,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
        }
        if IS_WIN:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        proc = subprocess.Popen(
            resolve_service_command(service, kind, executable),
            **kwargs,
        )

    service_pid_path(service).write_text(str(proc.pid), encoding="utf-8")
    print(
        f"  {service.name}: iniciado (pid={proc.pid}) "
        f"log={log_path.relative_to(ROOT)}"
    )


def stop_service(service: Service) -> None:
    pid = read_pid(service)
    pid_file = service_pid_path(service)
    if not pid:
        print(f"  {service.name}: sin pid")
        if pid_file.exists():
            pid_file.unlink()
        return

    if not is_running(pid):
        print(f"  {service.name}: no estaba corriendo")
        if pid_file.exists():
            pid_file.unlink()
        return

    if IS_WIN:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        os.kill(pid, signal.SIGTERM)

    if pid_file.exists():
        pid_file.unlink()
    print(f"  {service.name}: detenido")


def cmd_up(sync_deps: bool, use_postgres: bool) -> None:
    runner_kind, runner_executable = resolve_runner()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PID_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    print("== preparando entorno local (sin Docker/Podman) ==")
    print(f"== runner: {runner_kind} -> {runner_executable} ==")
    if use_postgres:
        print(
            "== TXNR productos con PostgreSQL local "
            "(fallback mock si falla) =="
        )
    for service in SERVICES:
        write_env_file(service, use_postgres)

    if sync_deps:
        if runner_kind == "uv":
            print("== instalando dependencias (uv sync) ==")
        else:
            print("== instalando dependencias (venv + pip) ==")
        for service in SERVICES:
            install_service_deps(service, runner_kind, runner_executable)
    else:
        print("== usando ambiente actual (sin reinstalar dependencias) ==")

    print("== levantando servicios prioritarios ==")
    for service in SERVICES:
        start_service(service, runner_kind, runner_executable)

    print(
        "\nStack local arriba:\n"
        "  - Agent:              http://127.0.0.1:8000/docs\n"
        "  - Back data:          http://127.0.0.1:8003/docs\n"
        "  - TXNR:               http://127.0.0.1:8004/docs\n"
        "  - TX ASO simulator:   http://127.0.0.1:8050/docs\n"
        "  - Doble cobro:        http://127.0.0.1:8006/docs\n"
        "  - Front test:         http://127.0.0.1:8501\n"
        "\nTXNR: todos los ASOs van al simulador (ASO_SOURCE=simulator).\n"
        "  Cliente de prueba compatible: user_id=1010223694\n"
        "    tarjeta mock: 4912680517944979 (ultimos 4: 4979, VISA)\n"
        "    fixture FO/ops: data/ en co_pqrs_back_trx_aso_simulator\n"
        "  Para aprobar el reto (subida-nivel):\n"
        "    POST :8050/security/v0/order-chanel/sim-4979-challenge/approve\n"
        "\nRevisar logs en scripts/.local_run/logs/*.log\n"
        "Parar todo: python scripts/run_local.py down\n"
        "Analitica local (RabbitMQ+Logstash -> OpenSearch): "
        "LOCAL_RABBITMQ_ENABLED=true python scripts/run_local.py up "
        "(ver co_pqrs_back_opensearch/docker-compose.analytics.yml)\n"
        "LLM real en vez de contingencia: LOCAL_LLM_REAL=true "
        "LOCAL_LLM_ENDPOINT=... LOCAL_LLM_API_KEY=... python scripts/run_local.py up"
    )


def cmd_down() -> None:
    print("== deteniendo servicios locales ==")
    for service in reversed(SERVICES):
        stop_service(service)


def cmd_status() -> None:
    print("== estado de servicios locales ==")
    for service in SERVICES:
        pid = read_pid(service)
        if pid and is_running(pid):
            print(f"  {service.name}: UP (pid={pid})")
        elif pid:
            print(f"  {service.name}: DOWN (pid huérfano={pid})")
        else:
            print(f"  {service.name}: DOWN")


def main() -> None:
    parser = argparse.ArgumentParser(description="Lanzador local host-only")
    parser.add_argument(
        "command",
        nargs="?",
        default="up",
        choices=["up", "down", "status"],
    )
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--use-postgres", action="store_true")
    args = parser.parse_args()

    if args.command == "up":
        cmd_up(sync_deps=args.sync, use_postgres=args.use_postgres)
    elif args.command == "down":
        cmd_down()
    else:
        cmd_status()


if __name__ == "__main__":
    main()
