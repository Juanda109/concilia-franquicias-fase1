from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ResolveResult, ScenarioIndex


class ScenarioResolver:
    """Resolve which JSON file to return for a request."""

    def __init__(self, data_dir: Path, index_file: str = "scenario_index.json") -> None:
        self.data_dir = data_dir
        self.index_file = index_file
        self.index = self._load_index()

    def resolve(
        self,
        *,
        document_type: str,
        document_number: str,
        last_name: str,
    ) -> ResolveResult:
        normalized_type = _normalize(document_type)
        normalized_number = _normalize(document_number)
        normalized_last_name = _normalize(last_name)

        # 1) Exact match by full query combination when lastName is provided.
        if normalized_last_name:
            for rule in self.index.by_query:
                if (
                    _normalize(rule.document_type) == normalized_type
                    and _normalize(rule.document_number) == normalized_number
                    and _normalize(rule.last_name) == normalized_last_name
                ):
                    return ResolveResult(
                        file_path=self.data_dir / rule.file,
                        strategy="query_exact",
                    )
        else:
            # 1.1) Match by documentType + documentNumber when lastName is missing.
            for rule in self.index.by_query:
                if (
                    _normalize(rule.document_type) == normalized_type
                    and _normalize(rule.document_number) == normalized_number
                ):
                    return ResolveResult(
                        file_path=self.data_dir / rule.file,
                        strategy="query_without_last_name",
                    )

        # Global default fallback.
        return ResolveResult(
            file_path=self.data_dir / self.index.default,
            strategy="default_fallback",
        )

    def read_payload(self, file_path: Path) -> dict[str, Any]:
        with file_path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)

        if isinstance(payload, dict):
            return payload

        return {"data": payload}

    def _load_index(self) -> ScenarioIndex:
        index_path = self.data_dir / self.index_file
        with index_path.open("r", encoding="utf-8") as stream:
            content = json.load(stream)

        return ScenarioIndex.model_validate(content)

def _normalize(value: str) -> str:
    return (value or "").strip().casefold()
