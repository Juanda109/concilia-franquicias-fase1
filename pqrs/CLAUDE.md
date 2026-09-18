# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. 



## What this repo is

Monorepo of Python microservices behind a PQRS (complaints/claims) chatbot for BBVA Colombia.
The centerpiece is `co_pqrs_back_agent`, a FastAPI conversational agent that routes a user's
free-text intent into one of ~20 **workflows** defined entirely in YAML, walks deterministic
steps, and uses an LLM only for routing/validation/closing. Everything else in the repo either
feeds it data, persists it, audits it, or deploys it.

**`docs/` is the declared source of truth** for what changed, the metrics dictionary, and how to
deploy/operate analytics. Read `docs/README.md` first — it has an orientation table. Keep it
updated when changing analytics, metrics, or daily limits.

The **root `README.md` is stale**: it documents a `src/agentepqr/` layout that no longer exists.
Trust `co_pqrs_back_agent/README.md` and `docs/` instead. Root `main.py` / `pyproject.toml` /
`aso_.py` are leftovers, not the real entry points.

## Services and ports

| Directory | Port | Role |
|---|---|---|
| `co_pqrs_back_agent` | 8000 | The bot. Routing + workflow engine + conversation persistence. |
| `co_pqrs_back_maintenance` | 8001 | Closes idle `Active` conversations, historizes `Closed` ones to MinIO/JSON. |
| `co_pqrs_back_error_handler` | 8002 | Receives agent failures, pulls the conversation from OpenSearch, dumps an analytics-ready JSON report. |
| `co_pqrs_back_data` | 8003 | Customer data (PostgreSQL / CSV mock / ASO), plus SMTP email sending. |
| `co_pqrs_back_trx_noreconocida` | 8004 | Unrecognized-transaction path. **Still a MOCK skeleton** — fixed `status: "mock"` responses. |
| `co_pqrs_back_commercial_info_simulator` | 8050 | Simulator of the commercial-information endpoint. |
| `co_pqrs_front_test` | 8501 | Streamlit test front-end + metrics viewer. |
| `co_pqrs_back_test_aso` | — | Mock of BBVA NextGen ASO core services (granting ticket, commercial info). |
| `co_pqrs_back_trx_aso_simulator` | 8050 | Simulator of the ASO services used by the trx flow (financial-overview, transactions, operations, Salesforce, blocks). |
| `co_pqrs_back_opensearch` | 9200 | Local OpenSearch + Dashboards compose stack for development. |
| `co_pqrs_back_load_ada_data`, `co_pqrs_back_load_seizures_data` | — | Batch/CronJob loaders (parquet / fixed-width files → PostgreSQL). |
| `co_pqrs_back_conversation_extractor` | — | CronJob every 30 min: MinIO conversations → Excel for Looker. |
| `co_pqrs_back_report` | — | CronJob: renders an OpenSearch Dashboards dashboard to PDF, mails it via internal SMTP. |
| `IaC/` | — | OpenShift/OKD kustomize manifests, per environment. |

## Commands

Each service is an independent `uv` project. Always `cd` into the service directory first —
running from the repo root picks up the stale root `pyproject.toml`.

```bash
cd co_pqrs_back_agent
uv sync

# run the API (note --app-dir src; the package root is src/, not the service dir)
uv run uvicorn --app-dir src infrastructure.entrypoint.fastapi_app:app --reload --host 127.0.0.1 --port 8000

# tests — conftest.py at the service root puts src/ on sys.path
uv run pytest
uv run pytest tests/test_application/test_chat_service.py
uv run pytest tests/test_application/test_chat_service.py::test_name
uv run pytest -k "centrales"
```

`co_pqrs_back_data` (8003), `co_pqrs_back_error_handler` (8002) and
`co_pqrs_back_trx_noreconocida` (8004) follow the identical pattern — same uvicorn target string,
just a different port.

Containers use **Podman** (`Containerfile`, not `Dockerfile`, for the core services):

```bash
cd co_pqrs_back_agent
podman compose up --build
```

Inside a container reaching a host-side OpenSearch, the endpoint is
`https://host.containers.internal:9200`.

There is no repo-wide linter. Only `co_pqrs_back_conversation_extractor` declares
`black`/`flake8`/`mypy` as dev deps; the rest have none.

## Architectural conventions

**Hexagonal layering, uniform across services.** `src/application/` (use cases) →
`src/domain/` (models + business rules, no I/O) → `src/infrastructure/` (`core/config.py`,
`core/logger.py`, `entrypoint/` FastAPI, `genai/`, `persistence/`, `messaging/`,
`observability/`). Routers validate and delegate; business logic does not live in routers.

**Imports are `src`-relative, not package-prefixed.** Code says `from domain.workflow.models
import ...`, never `from src.domain...`. This works because `--app-dir src` (runtime),
`PYTHONPATH=/app/src` (container), and the service-root `conftest.py` (tests) all put `src/` on
the path. New modules must follow this or they break in one of the three contexts.

**Config is `.env`-driven through `load_env_constants()`** in `infrastructure/core/config.py` —
file values merged with, and overridden by, real environment variables. Each typed loader
(`load_opensearch_settings`, `load_back_data_service_url`, …) reads through it. Don't call
`os.getenv` directly in new code. Start from `.env.example`.

**External calls are fail-open and non-blocking.** `back_data_client`, `trx_client`,
`error_handler_client`, `maintenance_client` and `event_publisher` use short timeouts, swallow
errors after logging, and are scheduled as detached tasks. A degraded dependency must never
change or slow the conversation turn. Preserve this when adding integrations.

## The workflow engine (the part that matters)

Routing and flows are **100% data-driven — adding a path normally touches no Python.** See
`co_pqrs_back_agent/docs/COMO_AGREGAR_UN_CAMINO.md` for the full checklist.

- `src/domain/workflow/general.yml` — the routing catalog. Groups (`hazlo_tu_mismo`,
  `guia_rapida`, `pqrs`, `preguntas_frecuentes`, …), and per-option the fields the LLM router
  reasons over: `description`, `preconditions`, `no_usar`, `se_confunde_con`, `examples`,
  `contraejemplos`, `limit_category`, `workflow`. The file's header comments document each field.
- `src/domain/workflow/<grupo>/<workflow>.yml` — the step tree for one flow: `version`,
  `start_step`, `steps` with `question`, `input_type` (`choice` | `text` | `terminal`),
  `options[].next_step`, `save_as`, optional `action`.
- `src/domain/workflow/routing_prompt.yml` — router persona and business few-shots.
- `src/domain/workflow/shared_steps.yml`, `general_messages.yml` — reusable steps/messages
  (satisfaction check, etc.).
- `workflow_engine.py` resolves a flow file as `<grupo>/<workflow>/<workflow>.yml` then
  `<grupo>/<workflow>.yml` (the latter is the recommended layout).

**The routing catalog is authoritative in YAML.** The routing Excel
(`routing_catalog_base_PQRS.xlsx`) is external reference material only — never make the agent
read a `.csv`/`.xlsx` at runtime; transcribe it into `general.yml` by hand.

`Conversation.workflow` is a plain `str` (not an enum) precisely so new flows need no code change.

**`action:` is the one escape hatch into Python.** A step's `action` string is dispatched by
`execute_workflow_action()` in `src/application/chat/workflow_actions.py` — an explicit
if-chain, not a registry. A new action means adding a branch there; an unknown action logs and
no-ops rather than failing.

`chat_service.py` (~3.6k lines) and `workflow_actions.py` (~3.2k lines) are the two large files —
orient with `grep` before reading.

## Conversation lifecycle and API contract

`POST /start` → `POST /chat` (repeat) → `POST /polling` + `GET /polling/{id}` → `POST /end`.

- `conversation_id` is **deterministic**: `{customer_id}_{yyyymmdd}` (e.g. `03966512_20260421`).
  `POST /start` takes `user_id` and generates it; it does not accept a `conversation_id`.
- `POST /chat` before `/start` → `404`. `/start` twice the same day while still `ACTIVE` → `409`.
  A `CLOSED` same-day session can be reopened (previous messages are cleared).
- **A turn over ~9 seconds returns `204 No Content`**, leaves the conversation `Running`, and
  keeps processing in the background. The client then polls: `POST /polling` returns `204` while
  busy, `303 See Other` with `Location: /polling/{id}` when done; `GET /polling/{id}` returns the
  final bot message. Any change to turn handling must keep this contract intact.
- Daily limits are enforced per user: `MAX_DAILY_SESSIONS` (sessions/day) and
  `MAX_DAILY_CATEGORY_INTERACTIONS` (3/day **per case**, counted via
  `workflow_engine.get_limit_key()`). `centrales_de_riesgo` is counted per subflow
  (`centrales_de_riesgo:<subflujo>`), not globally. Counters live in the `client-control-table`
  index and reset at Bogotá midnight — no cron.

## Two OpenSearch clusters — do not conflate them

- **Operational** (`IaC/BD/opensearch/`): live conversation state. Indices
  `conversations-reference` (conversation without the `messages` array),
  `conversations-messages` (all messages, reattached in memory on read), `client-control-table`.
- **Analytics** (`IaC/elk/opensearch-analytics/`): isolated cluster fed by
  agent → RabbitMQ `pqr.events` (fire-and-forget, gated by `RABBITMQ_ENABLED`) → Logstash (OSS
  image, OpenSearch output) → `pqr-metrics-*`, `pqr-conversations-*`, `logs-openshift-*`, ISM 30d
  retention → OpenSearch Dashboards → SMTP PDF CronJob. The legacy Elasticsearch/Kibana stack
  under `IaC/elk/elastic` and `IaC/elk/kibana` is **deprecated**.

Index templates are created by a bootstrap Job on purpose — purely dynamic mapping guesses types
and breaks aggregations. Field-by-field reference: `docs/METRICAS_CAMPOS_Y_VISUALIZACIONES.md`.

`data/*.json` files in the services are test fixtures / migration seed, not the runtime store.

## Environments and Git

Environment is **branch-based**, and `IaC/` is per-environment: `feature/PQRSdev` (dev),
`feature/PQRSqa` (QA), `feature/HiddenLeague` (PRD). **Never cross endpoints, image tags, or
secrets between branches.**

Commits follow `<type>(<scope>): [issue] <subject>` per `CONTRIBUTING.md` — types `feat`, `fix`,
`docs`, `refactor`, `test`, `chore`, `misc`. Note the existing history on this branch uses a
different in-house style (`PQRS-0000 <subject>`); match the surrounding history when in doubt.

CI (`.github/workflows/ci-app.yml`) delegates to an external reusable workflow
(`platform/reusable-workflows`), so it cannot be reproduced or debugged locally.

## Language

Identifiers, log messages and most docstrings are English (the `guardrail/` module is an
exception, documented in Spanish); user-facing conversation text, YAML workflow copy, READMEs and
`docs/` are Spanish. Match whichever convention the file you are editing already uses.
