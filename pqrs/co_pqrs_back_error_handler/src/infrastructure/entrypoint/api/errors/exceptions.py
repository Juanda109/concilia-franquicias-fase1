"""Custom exception types for the error handler service."""

from __future__ import annotations

from typing import Any


class ErrorHandlerError(Exception):
    """Base exception with serializable details."""

    default_message = "An unexpected application error occurred."
    error_code = "application_error"
    http_status_code = 500

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error": {
                "code": self.error_code,
                "message": self.message,
            }
        }
        if self.details:
            payload["error"]["details"] = self.details
        return payload


class ConfigurationError(ErrorHandlerError):
    """Raised when runtime configuration is invalid."""

    default_message = "Application configuration is invalid."
    error_code = "configuration_error"
    http_status_code = 500


class ExternalServiceError(ErrorHandlerError):
    """Raised when OpenSearch or another dependency fails."""

    default_message = "An external dependency failed."
    error_code = "external_service_error"
    http_status_code = 502


class ContextStorageError(ErrorHandlerError):
    """Raised when conversation context cannot be recovered."""

    default_message = "Conversation context could not be recovered."
    error_code = "context_storage_error"
    http_status_code = 500


class ReportPersistenceError(ErrorHandlerError):
    """Raised when the JSON report cannot be written locally."""

    default_message = "The report could not be persisted."
    error_code = "report_persistence_error"
    http_status_code = 500
