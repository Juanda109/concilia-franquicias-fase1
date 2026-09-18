#!/usr/bin/env python3
"""Barrido de datos sensibles en las trazas persistidas (MinIO o disco).

Busca, en cada objeto JSON / NDJSON, lo que el control KYNS IT 3 prohibe en
claro: numeros de tarjeta (13-19 digitos que empiezan por 2-6 y pasan Luhn, o
16 que empiezan por 4/5; los contratos del banco empiezan por 0/1 y no cuentan),
correos, el TSEC completo, contrasenas del granting sin enmascarar y volcados
``body_full``. Sirve para dos cosas: medir cuantos objetos historicos hay que
depurar y demostrar, tras la remediacion, que las trazas nuevas salen limpias.

Uso:
    # bucket de MinIO (variables MINIO_ENDPOINT_URL, MINIO_ROOT_USER, MINIO_ROOT_PASSWORD)
    python scripts/scan_sensitive_traces.py --bucket audit-logs --prefix clients/

    # carpeta local (p. ej. la salida de fallback del error handler)
    python scripts/scan_sensitive_traces.py --dir ./output

    # lista los objetos con hallazgos y un fragmento enmascarado de cada uno
    python scripts/scan_sensitive_traces.py --dir ./output --show 5

Sale con codigo 1 si hay hallazgos, 0 si no: se puede usar como gate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable, Iterator

PAN_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TSEC_RE = re.compile(r'"tsec_completo"\s*:\s*"[^"]{20,}"')
PASSWORD_RE = re.compile(r'"idAuthenticationData"\s*:\s*"password".{0,80}?"authenticationData"\s*:\s*\[\s*"(?!<oculto)[^"]+"', re.S)
BODY_FULL_RE = re.compile(r'"body_full"\s*:\s*(?!"<oculto>")[\[{"]')

CHECKS = {
    "pan": PAN_RE,
    "email": EMAIL_RE,
    "tsec_completo": TSEC_RE,
    "password_granting": PASSWORD_RE,
    "body_full": BODY_FULL_RE,
}


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def find(text: str) -> Counter:
    hits: Counter = Counter()
    for m in PAN_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if digits[:1] in "23456" and (_luhn(digits) or (len(digits) == 16 and digits[0] in "45")):
            hits["pan"] += 1
    for name, rx in CHECKS.items():
        if name == "pan":
            continue
        hits[name] += len(rx.findall(text))
    return +hits


def _mask(text: str) -> str:
    text = PAN_RE.sub(lambda m: "*" * 12 + re.sub(r"\D", "", m.group(0))[-4:], text)
    return EMAIL_RE.sub("***@***", text)


def iter_dir(root: Path) -> Iterator[tuple[str, str]]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in (".json", ".ndjson", ".txt", ".log"):
            try:
                yield str(path.relative_to(root)), path.read_text(errors="replace")
            except OSError:
                continue


def iter_bucket(bucket: str, prefix: str) -> Iterator[tuple[str, str]]:
    import boto3  # dependencia del error handler

    client = boto3.client(
        "s3",
        endpoint_url=os.environ["MINIO_ENDPOINT_URL"],
        aws_access_key_id=os.environ["MINIO_ROOT_USER"],
        aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
        region_name=os.getenv("MINIO_REGION", "us-east-1"),
    )
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.lower().endswith((".json", ".ndjson", ".txt", ".log")):
                continue
            body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
            yield key, body.decode("utf-8", errors="replace")


def scan(items: Iterable[tuple[str, str]], show: int) -> int:
    totals: Counter = Counter()
    objects = 0
    flagged: list[tuple[str, Counter, str]] = []
    for name, text in items:
        objects += 1
        hits = find(text)
        if hits:
            totals.update(hits)
            first = next((m.group(0) for rx in CHECKS.values() for m in [rx.search(text)] if m), "")
            flagged.append((name, hits, _mask(first)[:120]))
    print(f"objetos revisados : {objects}")
    print(f"objetos con hallazgos: {len(flagged)}")
    for kind in CHECKS:
        print(f"  {kind:<18}: {totals.get(kind, 0)}")
    for name, hits, snippet in flagged[:show]:
        print(f"- {name}: {dict(hits)} | {snippet}")
    if len(flagged) > show > 0:
        print(f"... y {len(flagged) - show} objetos mas (usa --show N)")
    return 1 if flagged else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--dir", type=Path, help="carpeta local con trazas")
    src.add_argument("--bucket", help="bucket de MinIO (requiere MINIO_* en el entorno)")
    parser.add_argument("--prefix", default="", help="prefijo dentro del bucket (p. ej. clients/)")
    parser.add_argument("--show", type=int, default=10, help="cuantos objetos con hallazgos listar")
    args = parser.parse_args()
    items = iter_dir(args.dir) if args.dir else iter_bucket(args.bucket, args.prefix)
    sys.exit(scan(items, args.show))


if __name__ == "__main__":
    main()
