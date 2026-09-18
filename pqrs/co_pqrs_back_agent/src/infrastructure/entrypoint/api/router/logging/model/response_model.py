from typing import Optional

from pydantic import BaseModel


class LogGroupResponse(BaseModel):
    configuredLevel: str
    members: Optional[list[str]]


class LogNameResponse(BaseModel):
    configuredLevel: str
    effectiveLevel: str


class LogResponse(BaseModel):
    levels: list[str]
    loggers: dict[str, LogNameResponse]
    groups: dict[str, LogGroupResponse]
