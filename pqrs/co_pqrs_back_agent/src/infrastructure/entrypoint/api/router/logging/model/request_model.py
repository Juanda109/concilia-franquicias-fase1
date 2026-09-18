import enum
import logging
from typing import Optional
import contextvars

from pydantic import BaseModel

LogLevel = enum.Enum(
    "LogLevel",
    {level: level for level in logging.getLevelNamesMapping().keys()},
)

conversation_id_ctx_var: contextvars.ContextVar[str] = contextvars.ContextVar("conversationId", default="global")


class LogRequest(BaseModel):
    configuredLevel: LogLevel
    duration: Optional[int] = 600


class RequestIDFilter(logging.Filter):
    def filter(self, record):

        request_id = conversation_id_ctx_var.get()
        # Append request_id to the message
        record.msg = f"{request_id} - {record.msg}"  # Modify the message to include request_id

        return True