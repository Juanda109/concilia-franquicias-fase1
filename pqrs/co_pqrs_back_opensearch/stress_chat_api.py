#!/usr/bin/env python3
"""Stress-test the chat API in parallel and save per-request timings to CSV.

Examples:
  python scripts/stress_chat_api.py --conversations 50 --concurrency 10
  python scripts/stress_chat_api.py --conversations 100 --concurrency 20 --timeout 30
  python scripts/stress_chat_api.py --conversations 20 --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from seed_conversations import (
    MESSAGES_INDEX,
    REFERENCE_INDEX,
    BANKS,
    CITIES,
    MERCHANTS,
    OpenSearchClient,
    digits,
    load_dotenv,
)


API_DEFAULT_BASE = "http://127.0.0.1:8000"
OUTPUT_DIRNAME = "results"


@dataclass(frozen=True)
class FlowTemplate:
    name: str
    builder_name: str
    messages: list[str]


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    dotenv_values = load_dotenv(repo_root / ".env")
    default_password = (
        os.getenv("OPENSEARCH_PASSWORD")
        or os.getenv("OPENSEARCH_INITIAL_ADMIN_PASSWORD")
        or dotenv_values.get("OPENSEARCH_INITIAL_ADMIN_PASSWORD")
        or "admin"
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=os.getenv("CHAT_API_URL", API_DEFAULT_BASE))
    parser.add_argument("--conversations", type=int, default=50, help="Total conversations to send.")
    parser.add_argument("--concurrency", type=int, default=10, help="Parallel conversations in flight.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout in seconds.")
    parser.add_argument(
        "--min-think-ms",
        type=int,
        default=0,
        help="Minimum pause between turns in the same conversation.",
    )
    parser.add_argument(
        "--max-think-ms",
        type=int,
        default=0,
        help="Maximum pause between turns in the same conversation.",
    )
    parser.add_argument("--seed", type=int, help="Optional random seed for reproducible runs.")
    parser.add_argument(
        "--output-dir",
        default=str(repo_root / OUTPUT_DIRNAME),
        help="Directory where the CSV file will be written.",
    )
    parser.add_argument(
        "--opensearch-host",
        default=os.getenv("OPENSEARCH_URL", "https://localhost:9200"),
    )
    parser.add_argument("--opensearch-username", default=os.getenv("OPENSEARCH_USERNAME", "admin"))
    parser.add_argument("--opensearch-password", default=default_password)
    parser.add_argument(
        "--skip-opensearch-check",
        action="store_true",
        help="Do not measure OpenSearch document counts before and after the run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate the conversations and output path without sending traffic.",
    )
    return parser.parse_args()


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_templates(rng: random.Random) -> list[FlowTemplate]:
    card_last4 = digits(rng, 4)
    unknown_amount = rng.randint(25_000, 950_000)
    unknown_date = (datetime.now(timezone.utc) - timedelta(days=rng.randint(1, 20))).date().isoformat()
    unknown_merchant = rng.choice(MERCHANTS)
    transfer_amount = rng.randint(40_000, 650_000)
    transfer_date = (datetime.now(timezone.utc) - timedelta(days=rng.randint(1, 10))).date().isoformat()
    bank_name = rng.choice(BANKS)
    city = rng.choice(CITIES)

    return [
        FlowTemplate(
            name="riesgo_perdida_tarjeta",
            builder_name="risk_card_loss",
            messages=["Hola", "Riesgo", "Perdida o robo", "Tarjeta", card_last4],
        ),
        FlowTemplate(
            name="riesgo_tx_tarjeta",
            builder_name="risk_unknown_card_tx",
            messages=[
                "Hola",
                "Riesgo",
                "Transaccion no reconocida",
                "Tarjeta",
                f"{unknown_date}, {unknown_amount}, compra no reconocida en {unknown_merchant}",
            ],
        ),
        FlowTemplate(
            name="riesgo_tx_cuenta",
            builder_name="risk_unknown_account_tx",
            messages=[
                "Hola",
                "Riesgo",
                "Transaccion no reconocida",
                "Cuenta",
                f"{transfer_date}, {transfer_amount}, transferencia no reconocida hacia {bank_name} desde {city}",
            ],
        ),
        FlowTemplate(
            name="solicitud_consulta_cuenta",
            builder_name="request_account_query",
            messages=["Hola", "Solicitud", "Consulta", "Cuenta", "Necesito saber el saldo y los ultimos movimientos."],
        ),
        FlowTemplate(
            name="solicitud_estado_tarjeta",
            builder_name="request_card_status",
            messages=["Hola", "Solicitud", "Estado", "Tarjeta", f"Quiero revisar el estado de la tarjeta terminada en {card_last4}."],
        ),
        FlowTemplate(
            name="test_prueba_1",
            builder_name="test_flow_1",
            messages=["Hola", "Test", "Prueba 1", "Cuenta", "Prueba automatizada de carga para validar el flujo."],
        ),
    ]


def choose_template(rng: random.Random) -> FlowTemplate:
    return rng.choice(build_templates(rng))


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def check_health(api_base: str, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(f"{api_base.rstrip('/')}/health", timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_chat(api_base: str, conversation_id: str, content: str, timeout: float) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    started_perf = time.perf_counter()
    request = urllib.request.Request(
        url=f"{api_base.rstrip('/')}/chat",
        data=json.dumps({"conversation_id": conversation_id, "content": content}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    status_code: int | None = None
    ok = False
    error_type = ""
    error_message = ""
    assistant_message = ""

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = response.status
            payload = json.loads(response.read().decode("utf-8"))
        assistant_message = str(payload.get("message", ""))
        ok = 200 <= status_code < 300
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        error_type = exc.__class__.__name__
        error_message = exc.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        error_type = exc.__class__.__name__
        error_message = str(exc)

    finished_at = datetime.now(timezone.utc)
    latency_ms = round((time.perf_counter() - started_perf) * 1000, 2)

    return {
        "started_at": iso_z(started_at),
        "finished_at": iso_z(finished_at),
        "latency_ms": latency_ms,
        "status_code": status_code if status_code is not None else "",
        "ok": ok,
        "assistant_message": assistant_message,
        "assistant_chars": len(assistant_message),
        "error_type": error_type,
        "error_message": error_message,
    }


def get_opensearch_counts(client: OpenSearchClient) -> dict[str, int]:
    reference_count = client.request("GET", f"/{REFERENCE_INDEX}/_count")
    messages_count = client.request("GET", f"/{MESSAGES_INDEX}/_count")
    return {
        REFERENCE_INDEX: int(reference_count["count"]),
        MESSAGES_INDEX: int(messages_count["count"]),
    }


def maybe_sleep_between_turns(rng: random.Random, min_ms: int, max_ms: int) -> None:
    if max_ms <= 0:
        return
    if min_ms > max_ms:
        min_ms, max_ms = max_ms, min_ms
    delay_ms = rng.randint(min_ms, max_ms)
    if delay_ms > 0:
        time.sleep(delay_ms / 1000)


def run_conversation(
    conversation_index: int,
    run_id: str,
    api_base: str,
    timeout: float,
    min_think_ms: int,
    max_think_ms: int,
    seed: int | None,
) -> list[dict[str, Any]]:
    rng = random.Random((seed or 0) + conversation_index)
    template = choose_template(rng)
    conversation_id = str(uuid.uuid4())
    rows: list[dict[str, Any]] = []

    for turn_index, message in enumerate(template.messages, start=1):
        result = post_chat(api_base, conversation_id, message, timeout)
        rows.append(
            {
                "run_id": run_id,
                "conversation_index": conversation_index,
                "conversation_id": conversation_id,
                "template": template.name,
                "turn": turn_index,
                "user_message": message,
                **result,
            }
        )

        if not result["ok"]:
            break
        if turn_index < len(template.messages):
            maybe_sleep_between_turns(rng, min_think_ms, max_think_ms)

    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "run_id",
        "conversation_index",
        "conversation_id",
        "template",
        "turn",
        "user_message",
        "started_at",
        "finished_at",
        "latency_ms",
        "status_code",
        "ok",
        "assistant_chars",
        "assistant_message",
        "error_type",
        "error_message",
    ]
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [float(row["latency_ms"]) for row in rows]
    ok_rows = [row for row in rows if row["ok"]]
    failed_rows = [row for row in rows if not row["ok"]]
    status_counts: dict[str, int] = {}
    template_counts: dict[str, int] = {}

    for row in rows:
        status_key = str(row["status_code"] or row["error_type"] or "unknown")
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
        template_counts[row["template"]] = template_counts.get(row["template"], 0) + 1

    return {
        "requests": len(rows),
        "successes": len(ok_rows),
        "failures": len(failed_rows),
        "success_rate_pct": round((len(ok_rows) / len(rows) * 100) if rows else 0.0, 2),
        "latency_ms_p50": round(percentile(latencies, 0.50), 2),
        "latency_ms_p95": round(percentile(latencies, 0.95), 2),
        "latency_ms_max": round(max(latencies) if latencies else 0.0, 2),
        "status_counts": status_counts,
        "template_counts": template_counts,
    }


def print_dry_run(args: argparse.Namespace, csv_path: Path) -> None:
    rng = random.Random(args.seed)
    print(f"Dry run only. CSV target: {csv_path}")
    print("Sample templates:")
    for _ in range(min(args.conversations, 5)):
        template = choose_template(rng)
        print(f"  - {template.name}: {template.messages}")


def main() -> int:
    args = parse_args()
    if args.conversations < 1:
        raise ValueError("--conversations must be at least 1")
    if args.concurrency < 1:
        raise ValueError("--concurrency must be at least 1")

    run_id = f"chat-stress-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    csv_path = Path(args.output_dir) / f"{run_id}.csv"

    if args.dry_run:
        print_dry_run(args, csv_path)
        return 0

    health = check_health(args.api_base, args.timeout)
    print(f"API health: {health}")

    before_counts: dict[str, int] | None = None
    after_counts: dict[str, int] | None = None
    opensearch_error = ""

    if not args.skip_opensearch_check:
        try:
            client = OpenSearchClient(
                host=args.opensearch_host,
                username=args.opensearch_username,
                password=args.opensearch_password,
                verify_ssl=False,
            )
            before_counts = get_opensearch_counts(client)
        except Exception as exc:  # noqa: BLE001
            opensearch_error = str(exc)

    rows: list[dict[str, Any]] = []
    started_at = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(
                run_conversation,
                index,
                run_id,
                args.api_base,
                args.timeout,
                args.min_think_ms,
                args.max_think_ms,
                args.seed,
            )
            for index in range(1, args.conversations + 1)
        ]
        for future in as_completed(futures):
            rows.extend(future.result())

    total_elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    rows.sort(key=lambda row: (row["conversation_index"], row["turn"]))
    write_csv(csv_path, rows)

    if not args.skip_opensearch_check and not opensearch_error:
        try:
            client = OpenSearchClient(
                host=args.opensearch_host,
                username=args.opensearch_username,
                password=args.opensearch_password,
                verify_ssl=False,
            )
            after_counts = get_opensearch_counts(client)
        except Exception as exc:  # noqa: BLE001
            opensearch_error = str(exc)

    summary = summarise(rows)
    print(f"Run ID: {run_id}")
    print(f"CSV: {csv_path}")
    print(f"Elapsed: {total_elapsed_ms} ms")
    print(f"Requests: {summary['requests']}")
    print(f"Successes: {summary['successes']}")
    print(f"Failures: {summary['failures']}")
    print(f"Success rate: {summary['success_rate_pct']}%")
    print(f"Latency p50: {summary['latency_ms_p50']} ms")
    print(f"Latency p95: {summary['latency_ms_p95']} ms")
    print(f"Latency max: {summary['latency_ms_max']} ms")
    print(f"Status counts: {json.dumps(summary['status_counts'], ensure_ascii=True)}")
    print(f"Template counts: {json.dumps(summary['template_counts'], ensure_ascii=True)}")

    if before_counts and after_counts:
        reference_delta = after_counts[REFERENCE_INDEX] - before_counts[REFERENCE_INDEX]
        messages_delta = after_counts[MESSAGES_INDEX] - before_counts[MESSAGES_INDEX]
        print(
            "OpenSearch delta: "
            f"{REFERENCE_INDEX} {before_counts[REFERENCE_INDEX]} -> {after_counts[REFERENCE_INDEX]} "
            f"(+{reference_delta}), "
            f"{MESSAGES_INDEX} {before_counts[MESSAGES_INDEX]} -> {after_counts[MESSAGES_INDEX]} "
            f"(+{messages_delta})"
        )
    elif opensearch_error:
        print(f"OpenSearch delta unavailable: {opensearch_error}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted by user.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
