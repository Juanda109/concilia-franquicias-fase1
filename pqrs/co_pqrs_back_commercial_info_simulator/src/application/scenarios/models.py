from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class QueryScenarioRule(BaseModel):
    document_type: str = Field(default="")
    document_number: str = Field(default="")
    last_name: str = Field(default="")
    file: str


class ScenarioIndex(BaseModel):
    default: str
    by_document: dict[str, str] = Field(default_factory=dict)
    by_query: list[QueryScenarioRule] = Field(default_factory=list)


class ResolveResult(BaseModel):
    file_path: Path
    strategy: str
