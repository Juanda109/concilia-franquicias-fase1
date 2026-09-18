from __future__ import annotations

import re


INVALID_PATH_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_path_component(value: str) -> str:
    sanitized = INVALID_PATH_CHARS.sub("_", value).strip("._")
    return sanitized or "unknown"
