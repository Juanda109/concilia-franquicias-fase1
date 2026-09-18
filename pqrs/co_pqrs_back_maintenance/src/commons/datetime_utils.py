from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo


def extract_first_datetime(
    source: dict[str, Any],
    field_names: list[str],
    default_timezone: str,
) -> datetime | None:
    for field_name in field_names:
        value = get_field(source, field_name)
        parsed = parse_datetime(value, default_timezone)
        if parsed is not None:
            return parsed
    return None


def get_field(payload: dict[str, Any], field_name: str) -> Any:
    if field_name in payload:
        return payload[field_name]

    current: Any = payload
    for part in field_name.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def parse_datetime(value: Any, default_timezone: str) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return normalize_datetime(value, default_timezone)

    if isinstance(value, (int, float)):
        return from_epoch(value)

    if isinstance(value, str):
        raw_value = value.strip()
        if not raw_value:
            return None

        if raw_value.isdigit():
            return from_epoch(int(raw_value))

        normalized = raw_value.replace("Z", "+00:00")
        try:
            return normalize_datetime(datetime.fromisoformat(normalized), default_timezone)
        except ValueError:
            pass

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return normalize_datetime(datetime.strptime(raw_value, fmt), default_timezone)
            except ValueError:
                continue

    return None


def normalize_datetime(value: datetime, default_timezone: str) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=ZoneInfo(default_timezone)).astimezone(UTC)
    return value.astimezone(UTC)


def from_epoch(value: int | float) -> datetime:
    timestamp = float(value)
    if abs(timestamp) > 100_000_000_000:
        timestamp = timestamp / 1000
    return datetime.fromtimestamp(timestamp, tz=UTC)
