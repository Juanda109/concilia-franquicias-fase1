#!/usr/bin/env python3
"""Generate and upload simulated conversations to OpenSearch.

Examples:
  python scripts/seed_conversations.py --count 50
  python scripts/seed_conversations.py --count 120 --host https://localhost:9200
  python scripts/seed_conversations.py --count 50 --dry-run
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
import ssl
import sys
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REFERENCE_INDEX = "conversations-reference"
MESSAGES_INDEX = "conversations-messages"

REFERENCE_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "conversation_id": {"type": "keyword"},
            "first_msg_date": {"type": "date"},
            "last_msg_date": {"type": "date"},
            "status": {"type": "keyword"},
            "current_step": {"type": "keyword"},
            "workflow": {"type": "keyword"},
            "flow_version": {"type": "integer"},
            "flow_answers": {"type": "object", "enabled": True},
            "captured_data": {"type": "object", "enabled": True},
            "user_id": {"type": "keyword"},
        }
    },
}

MESSAGES_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "conversation_id": {"type": "keyword"},
            "id": {"type": "keyword"},
            "role": {"type": "keyword"},
            "content": {"type": "text"},
            "tokens": {
                "properties": {
                    "input_tokens": {"type": "integer"},
                    "output_tokens": {"type": "integer"},
                    "total_tokens": {"type": "integer"},
                }
            },
            "timing": {
                "properties": {
                    "received_at": {"type": "date"},
                    "responded_at": {"type": "date"},
                    "total_duration_ms": {"type": "integer"},
                }
            },
        }
    },
}

FIRST_NAMES = [
    "Ana",
    "Luis",
    "Maria",
    "Carlos",
    "Sofia",
    "Diego",
    "Laura",
    "Andres",
    "Camila",
    "Julian",
    "Valeria",
    "Nicolas",
    "Paula",
    "Jorge",
]

CITIES = [
    "Bogota",
    "Medellin",
    "Cali",
    "Barranquilla",
    "Bucaramanga",
    "Cartagena",
    "Pereira",
    "Manizales",
    "Santa Marta",
    "Tunja",
]

MERCHANTS = [
    "Mercado Centro",
    "Gas Express",
    "Mundo Hogar",
    "Tecno Plus",
    "Cafe del Parque",
    "Farmacia Central",
    "Rappi",
    "Viajes del Sol",
    "Super Ahorro",
    "Electro Plaza",
]

BANKS = [
    "Banco Andino",
    "Banco Capital",
    "Banco del Norte",
    "Finanzas Uno",
    "Cooperativa Central",
]

DEVICES = ["Android", "iPhone", "Huawei", "Samsung", "Xiaomi"]
BROWSERS = ["Chrome", "Safari", "Edge"]
ACCOUNT_TYPES = ["ahorros", "corriente"]


@dataclass
class Scenario:
    workflow: str
    status: str
    current_step: str
    flow_version: int
    flow_answers: dict[str, Any]
    captured_data: dict[str, Any]
    turns: list[tuple[str, str]]


class OpenSearchClient:
    def __init__(self, host: str, username: str, password: str, verify_ssl: bool) -> None:
        self.host = host.rstrip("/")
        token = f"{username}:{password}".encode("ascii")
        self.auth_header = base64.b64encode(token).decode("ascii")
        self.ssl_context = ssl.create_default_context()
        if not verify_ssl:
            self.ssl_context.check_hostname = False
            self.ssl_context.verify_mode = ssl.CERT_NONE

    def request(
        self,
        method: str,
        path: str,
        body: Any | None = None,
        headers: dict[str, str] | None = None,
        expected: tuple[int, ...] = (200, 201),
    ) -> Any:
        request_headers = {"Authorization": f"Basic {self.auth_header}"}
        request_body: bytes | None = None

        if headers:
            request_headers.update(headers)

        if body is not None:
            if isinstance(body, bytes):
                request_body = body
            elif isinstance(body, str):
                request_body = body.encode("utf-8")
            else:
                request_headers.setdefault("Content-Type", "application/json")
                request_body = json.dumps(body).encode("utf-8")

        request = urllib.request.Request(
            url=f"{self.host}{path}",
            data=request_body,
            headers=request_headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(request, context=self.ssl_context) as response:
                raw = response.read().decode("utf-8")
                if response.status not in expected:
                    raise RuntimeError(
                        f"{method} {path} returned unexpected status {response.status}: {raw}"
                    )
                if not raw:
                    return None
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return raw
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"{method} {path} failed with status {exc.code}: {error_body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not connect to {self.host}: {exc.reason}") from exc


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
    parser.add_argument("--host", default=os.getenv("OPENSEARCH_URL", "https://localhost:9200"))
    parser.add_argument("--username", default=os.getenv("OPENSEARCH_USERNAME", "admin"))
    parser.add_argument("--password", default=default_password)
    parser.add_argument("--count", type=int, default=50, help="Number of conversations to create.")
    parser.add_argument(
        "--prefix",
        default=f"sim-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        help="Prefix used for conversation and message IDs.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Optional random seed for reproducible output.",
    )
    parser.add_argument(
        "--verify-ssl",
        action="store_true",
        help="Verify SSL certificates. Disabled by default for local demo clusters.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate the data without sending it to OpenSearch.",
    )
    return parser.parse_args()


def load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        value = value.strip()
        if " #" in value and not value.startswith(("'", '"')):
            value = value.split(" #", 1)[0].strip()
        values[key.strip()] = value.strip().strip("'\"")
    return values


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def digits(rng: random.Random, length: int) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(length))


def estimate_tokens(text: str) -> int:
    return max(4, int(len(text.split()) * 1.35))


def pick_user_pool(rng: random.Random, count: int) -> list[str]:
    base_size = max(10, min(25, count // 2))
    return [f"user-{i:03d}" for i in range(1, base_size + 1)]


def build_card_loss(rng: random.Random, customer_name: str) -> Scenario:
    card_last4 = digits(rng, 4)
    city = rng.choice(CITIES)
    resolved = rng.random() < 0.82
    status = "Closed" if resolved else rng.choice(["Open", "Pending"])
    current_step = str(rng.randint(7, 9) if resolved else rng.randint(3, 6))
    replacement_days = rng.randint(2, 5)
    turns = [
        ("user", f"Hola, soy {customer_name}. Perdi mi tarjeta terminada en {card_last4} y necesito bloquearla."),
        ("assistant", "Puedo ayudarte con el bloqueo preventivo. Confirmame si la tarjeta es debito o credito."),
        ("user", f"Es credito. La perdi hoy en {city} y no la encuentro desde hace una hora."),
        ("assistant", f"Gracias. Ya deje el bloqueo preventivo activo para la tarjeta {card_last4}."),
    ]
    if resolved:
        turns.extend(
            [
                ("user", "Perfecto, tambien quiero pedir la reposicion."),
                (
                    "assistant",
                    f"Listo, la reposicion quedo registrada y la nueva tarjeta llegara en aproximadamente {replacement_days} dias habiles.",
                ),
            ]
        )
    else:
        turns.extend(
            [
                ("user", "Quedo bloqueada de inmediato o debo esperar confirmacion?"),
                (
                    "assistant",
                    "El bloqueo ya quedo aplicado. La reposicion sigue en revision y te avisaremos cuando el caso avance al siguiente paso.",
                ),
            ]
        )
    return Scenario(
        workflow="Riesgo",
        status=status,
        current_step=current_step,
        flow_version=1,
        flow_answers={
            "risk_type": "perdida",
            "perdida_tipo": "tarjeta",
            "perdida_tarjeta_referencia": card_last4,
            "city": city,
        },
        captured_data={
            "customer_name": customer_name,
            "card_last4": card_last4,
            "city": city,
        },
        turns=turns,
    )


def build_unknown_charge(rng: random.Random, customer_name: str) -> Scenario:
    amount = rng.randint(40_000, 980_000)
    merchant = rng.choice(MERCHANTS)
    city = rng.choice(CITIES)
    card_last4 = digits(rng, 4)
    resolved = rng.random() < 0.55
    status = "Closed" if resolved else rng.choice(["Open", "Pending"])
    current_step = str(rng.randint(8, 10) if resolved else rng.randint(4, 7))
    turns = [
        (
            "user",
            f"Buenas, veo un cobro por {amount} pesos en {merchant} y yo no hice esa compra con la tarjeta {card_last4}.",
        ),
        ("assistant", "Voy a revisar el movimiento. Confirmame por favor si la tarjeta sigue en tu poder."),
        ("user", f"Si, la tengo conmigo en {city} y nunca estuve en ese comercio."),
    ]
    if resolved:
        turns.extend(
            [
                (
                    "assistant",
                    "Gracias. El caso quedo marcado como compra no reconocida y ya dejamos la tarjeta bloqueada por seguridad.",
                ),
                ("user", "Tambien necesito el radicado para hacer seguimiento."),
                ("assistant", f"Claro, tu reclamacion quedo radicada y el ajuste provisional se vera reflejado en un maximo de 5 dias habiles."),
            ]
        )
    else:
        turns.extend(
            [
                ("assistant", "Ya radique el reclamo y escale la revision al equipo de fraude."),
                ("user", "Entendido, quedo pendiente del resultado."),
                ("assistant", "Perfecto, te notificaremos cuando tengamos la validacion del comercio."),
            ]
        )
    return Scenario(
        workflow="Riesgo",
        status=status,
        current_step=current_step,
        flow_version=2,
        flow_answers={
            "risk_type": "compra_no_reconocida",
            "merchant": merchant,
            "amount": amount,
            "city": city,
            "card_last4": card_last4,
        },
        captured_data={
            "customer_name": customer_name,
            "merchant": merchant,
            "amount": amount,
            "card_last4": card_last4,
        },
        turns=turns,
    )


def build_transfer_issue(rng: random.Random, customer_name: str) -> Scenario:
    amount = rng.randint(25_000, 750_000)
    bank = rng.choice(BANKS)
    reference = f"TRX-{digits(rng, 8)}"
    account_type = rng.choice(ACCOUNT_TYPES)
    resolved = rng.random() < 0.6
    status = "Closed" if resolved else rng.choice(["Open", "Pending"])
    current_step = str(rng.randint(6, 9) if resolved else rng.randint(2, 5))
    turns = [
        (
            "user",
            f"Hola, hice una transferencia de {amount} pesos a {bank} y el destinatario aun no la ve. El numero de referencia es {reference}.",
        ),
        ("assistant", "Te ayudo a validarla. Confirmame el tipo de cuenta desde donde salio el dinero."),
        ("user", f"Salio de mi cuenta de {account_type}."),
    ]
    if resolved:
        turns.extend(
            [
                (
                    "assistant",
                    "Gracias. La transferencia estaba en cola de compensacion y ya quedo liberada correctamente.",
                ),
                ("user", "Perfecto, entonces no debo hacer nada mas?"),
                ("assistant", "No, la operacion quedo normalizada y el beneficiario deberia verla reflejada hoy mismo."),
            ]
        )
    else:
        turns.extend(
            [
                ("assistant", "La operacion sigue en validacion interbancaria y quedo escalada para revision manual."),
                ("user", "Listo, espero entonces."),
                ("assistant", "Te avisaremos en cuanto tengamos respuesta del banco destino."),
            ]
        )
    return Scenario(
        workflow="Pagos",
        status=status,
        current_step=current_step,
        flow_version=1,
        flow_answers={
            "payment_type": "transferencia",
            "bank_destination": bank,
            "reference": reference,
            "amount": amount,
            "source_account_type": account_type,
        },
        captured_data={
            "customer_name": customer_name,
            "reference": reference,
            "amount": amount,
            "bank_destination": bank,
        },
        turns=turns,
    )


def build_payment_reversal(rng: random.Random, customer_name: str) -> Scenario:
    amount = rng.randint(20_000, 340_000)
    merchant = rng.choice(MERCHANTS)
    approval_code = digits(rng, 6)
    resolved = rng.random() < 0.72
    status = "Closed" if resolved else rng.choice(["Open", "Pending"])
    current_step = str(rng.randint(5, 8) if resolved else rng.randint(2, 5))
    turns = [
        (
            "user",
            f"Necesito ayuda con una devolucion por {amount} pesos en {merchant}. El comercio dice que ya reverso el pago pero yo no veo el dinero.",
        ),
        ("assistant", "Voy a revisar la reversa. Tienes a la mano el codigo de aprobacion de la compra?"),
        ("user", f"Si, el codigo es {approval_code}."),
    ]
    if resolved:
        turns.extend(
            [
                ("assistant", "Gracias. Ya confirme la reversa y el ajuste quedo aplicado en tu saldo disponible."),
                ("user", "Perfecto, gracias por la ayuda."),
                ("assistant", "Con gusto, el caso quedo cerrado."),
            ]
        )
    else:
        turns.extend(
            [
                ("assistant", "El comercio envio la reversa, pero la conciliacion aun sigue pendiente."),
                ("user", "Cuanto tiempo se puede demorar?"),
                ("assistant", "Puede tardar hasta 5 dias habiles. Te avisaremos apenas el ajuste sea procesado."),
            ]
        )
    return Scenario(
        workflow="Pagos",
        status=status,
        current_step=current_step,
        flow_version=2,
        flow_answers={
            "payment_type": "reversa",
            "merchant": merchant,
            "approval_code": approval_code,
            "amount": amount,
        },
        captured_data={
            "customer_name": customer_name,
            "merchant": merchant,
            "approval_code": approval_code,
            "amount": amount,
        },
        turns=turns,
    )


def build_login_support(rng: random.Random, customer_name: str) -> Scenario:
    device = rng.choice(DEVICES)
    browser = rng.choice(BROWSERS)
    error_code = f"E{digits(rng, 3)}"
    resolved = rng.random() < 0.78
    status = "Closed" if resolved else rng.choice(["Open", "Pending"])
    current_step = str(rng.randint(4, 7) if resolved else rng.randint(2, 4))
    turns = [
        (
            "user",
            f"Hola, no puedo entrar a la app desde mi {device}. Me sale el error {error_code} cuando intento iniciar sesion.",
        ),
        ("assistant", "Vamos a revisarlo. Tambien te pasa por navegador?"),
        ("user", f"Si, por {browser} tambien me rechaza el acceso."),
    ]
    if resolved:
        turns.extend(
            [
                ("assistant", "Gracias. Ya reinicie el perfil de autenticacion y te envie un nuevo enlace para restablecer la clave."),
                ("user", "Listo, ya pude entrar otra vez."),
                ("assistant", "Excelente, dejamos el caso cerrado."),
            ]
        )
    else:
        turns.extend(
            [
                ("assistant", "Ya escale el evento al equipo tecnico porque el error sigue activo en mas de un canal."),
                ("user", "Quedo pendiente entonces."),
                ("assistant", "Si, apenas tengamos respuesta te notificaremos por este mismo canal."),
            ]
        )
    return Scenario(
        workflow="Soporte",
        status=status,
        current_step=current_step,
        flow_version=3,
        flow_answers={
            "support_type": "acceso",
            "device": device,
            "browser": browser,
            "error_code": error_code,
        },
        captured_data={
            "customer_name": customer_name,
            "device": device,
            "browser": browser,
            "error_code": error_code,
        },
        turns=turns,
    )


def build_atm_claim(rng: random.Random, customer_name: str) -> Scenario:
    amount = rng.randint(50_000, 1_000_000)
    city = rng.choice(CITIES)
    atm_id = f"ATM-{digits(rng, 5)}"
    resolved = rng.random() < 0.48
    status = "Closed" if resolved else rng.choice(["Open", "Pending"])
    current_step = str(rng.randint(7, 9) if resolved else rng.randint(3, 6))
    turns = [
        (
            "user",
            f"Buenas, hice un retiro por {amount} pesos en el cajero {atm_id} de {city} y el cajero no entrego el efectivo.",
        ),
        ("assistant", "Lamento el inconveniente. Voy a revisar el evento con el cajero y tu cuenta."),
        ("user", "Gracias, necesito saber si me van a devolver el dinero."),
    ]
    if resolved:
        turns.extend(
            [
                ("assistant", "Ya confirmamos la falla del cajero y el dinero fue reversado a tu cuenta."),
                ("user", "Perfecto, ya veo el saldo actualizado."),
                ("assistant", "Excelente, dejamos el reclamo cerrado."),
            ]
        )
    else:
        turns.extend(
            [
                ("assistant", "El caso quedo radicado y estamos validando la auditoria del cajero."),
                ("user", "Entendido, gracias."),
                ("assistant", "Cuando termine la conciliacion te notificaremos el resultado."),
            ]
        )
    return Scenario(
        workflow="Reclamos",
        status=status,
        current_step=current_step,
        flow_version=1,
        flow_answers={
            "claim_type": "retiro_no_entregado",
            "atm_id": atm_id,
            "city": city,
            "amount": amount,
        },
        captured_data={
            "customer_name": customer_name,
            "atm_id": atm_id,
            "city": city,
            "amount": amount,
        },
        turns=turns,
    )


SCENARIO_BUILDERS = [
    build_card_loss,
    build_unknown_charge,
    build_transfer_issue,
    build_payment_reversal,
    build_login_support,
    build_atm_claim,
]


def generate_message_docs(
    conversation_id: str,
    turns: list[tuple[str, str]],
    start_at: datetime,
    rng: random.Random,
) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    cursor = start_at
    running_context_tokens = rng.randint(12, 28)

    for index, (role, content) in enumerate(turns, start=1):
        content_tokens = estimate_tokens(content)
        if role == "user":
            input_tokens = content_tokens
            output_tokens = 0
            duration_ms = rng.randint(10, 120)
        else:
            input_tokens = min(2048, running_context_tokens + rng.randint(10, 40))
            output_tokens = content_tokens
            duration_ms = rng.randint(900, 3200)

        responded_at = cursor + timedelta(milliseconds=duration_ms)
        message_id = f"{conversation_id}-msg-{index:02d}"

        docs.append(
            {
                "conversation_id": conversation_id,
                "id": message_id,
                "role": role,
                "content": content,
                "tokens": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
                "timing": {
                    "received_at": iso_z(cursor),
                    "responded_at": iso_z(responded_at),
                    "total_duration_ms": duration_ms,
                },
            }
        )

        running_context_tokens = min(2048, running_context_tokens + content_tokens)
        cursor = responded_at + timedelta(seconds=rng.randint(12, 90))

    return docs


def generate_documents(
    count: int,
    prefix: str,
    rng: random.Random,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if count < 1:
        raise ValueError("--count must be at least 1")

    now = datetime.now(timezone.utc)
    user_pool = pick_user_pool(rng, count)
    references: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []

    for index in range(1, count + 1):
        conversation_id = f"{prefix}-{index:03d}"
        user_id = rng.choice(user_pool)
        customer_name = rng.choice(FIRST_NAMES)
        start_at = now - timedelta(
            days=rng.randint(1, 60),
            hours=rng.randint(0, 23),
            minutes=rng.randint(0, 59),
            seconds=rng.randint(0, 59),
        )
        scenario_builder = rng.choice(SCENARIO_BUILDERS)
        scenario = scenario_builder(rng, customer_name)
        message_docs = generate_message_docs(conversation_id, scenario.turns, start_at, rng)

        references.append(
            {
                "conversation_id": conversation_id,
                "first_msg_date": message_docs[0]["timing"]["received_at"],
                "last_msg_date": message_docs[-1]["timing"]["responded_at"],
                "status": scenario.status,
                "current_step": scenario.current_step,
                "workflow": scenario.workflow,
                "flow_version": scenario.flow_version,
                "flow_answers": scenario.flow_answers,
                "captured_data": scenario.captured_data,
                "user_id": user_id,
            }
        )
        messages.extend(message_docs)

    return references, messages


def ensure_index(client: OpenSearchClient, index_name: str, mapping: dict[str, Any]) -> None:
    try:
        client.request("PUT", f"/{index_name}", body=mapping)
        print(f"Created index: {index_name}")
    except RuntimeError as exc:
        if "resource_already_exists_exception" in str(exc):
            print(f"Index already exists: {index_name}")
            return
        raise


def bulk_insert(
    client: OpenSearchClient,
    references: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    lines: list[str] = []
    for doc in references:
        lines.append(json.dumps({"index": {"_index": REFERENCE_INDEX, "_id": doc["conversation_id"]}}))
        lines.append(json.dumps(doc))
    for doc in messages:
        lines.append(json.dumps({"index": {"_index": MESSAGES_INDEX, "_id": doc["id"]}}))
        lines.append(json.dumps(doc))

    payload = "\n".join(lines) + "\n"
    response = client.request(
        "POST",
        "/_bulk?refresh=true",
        body=payload,
        headers={"Content-Type": "application/x-ndjson"},
    )
    if response.get("errors"):
        failed = [
            item
            for item in response.get("items", [])
            if item.get("index", {}).get("error")
        ]
        sample = json.dumps(failed[:3], indent=2)
        raise RuntimeError(f"Bulk insert completed with errors. Sample:\n{sample}")
    return response


def print_dry_run_summary(references: list[dict[str, Any]], messages: list[dict[str, Any]]) -> None:
    workflow_counts = Counter(doc["workflow"] for doc in references)
    print(json.dumps({"conversations": len(references), "messages": len(messages)}, indent=2))
    print("\nWorkflows:")
    for workflow, total in sorted(workflow_counts.items()):
        print(f"  - {workflow}: {total}")

    first_reference = references[0]
    first_conversation_messages = [doc for doc in messages if doc["conversation_id"] == first_reference["conversation_id"]]

    print("\nSample conversation reference:")
    print(json.dumps(first_reference, indent=2))
    print("\nSample messages:")
    print(json.dumps(first_conversation_messages[:3], indent=2))


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    references, messages = generate_documents(args.count, args.prefix, rng)

    if args.dry_run:
        print_dry_run_summary(references, messages)
        return 0

    client = OpenSearchClient(
        host=args.host,
        username=args.username,
        password=args.password,
        verify_ssl=args.verify_ssl,
    )

    client.request("GET", "/")
    ensure_index(client, REFERENCE_INDEX, REFERENCE_MAPPING)
    ensure_index(client, MESSAGES_INDEX, MESSAGES_MAPPING)
    bulk_insert(client, references, messages)

    workflow_counts = Counter(doc["workflow"] for doc in references)
    print(f"Inserted {len(references)} conversations and {len(messages)} messages.")
    print(f"Prefix: {args.prefix}")
    print("Workflows:")
    for workflow, total in sorted(workflow_counts.items()):
        print(f"  - {workflow}: {total}")
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
