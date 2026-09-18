"""Shared exception types for the project."""

from typing import Any


class AgentepqrError(Exception):
    """
    Base exception for all custom project errors.

    This base class centralizes a human-readable message, a stable error code,
    an optional HTTP status code, and a details payload that can later be
    exposed by API exception handlers.
    """

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
        """
        Return a serializable representation of the exception.
        """

        payload: dict[str, Any] = {
            "error": {
                "code": self.error_code,
                "message": self.message,
            }
        }

        if self.details:
            payload["error"]["details"] = self.details

        return payload


class ConfigurationError(AgentepqrError):
    """
    Raised when required application configuration is missing or invalid.
    """

    default_message = "Application configuration is invalid."
    error_code = "configuration_error"
    http_status_code = 500


class ResourceNotFoundError(AgentepqrError):
    """
    Raised when an expected resource cannot be found.
    """

    default_message = "Requested resource was not found."
    error_code = "resource_not_found"
    http_status_code = 404


class ConflictError(AgentepqrError):
    """
    Raised when an operation cannot be completed because the resource state conflicts.
    """

    default_message = "The operation conflicts with the current resource state."
    error_code = "conflict_error"
    http_status_code = 409


class InvalidOperationError(AgentepqrError):
    """
    Raised when a request or workflow transition is not valid for the current state.
    """

    default_message = "The requested operation is not valid in the current state."
    error_code = "invalid_operation"
    http_status_code = 400


class AuthenticationError(AgentepqrError):
    """
    Raised when a request cannot be authenticated.
    """

    default_message = "Authentication failed."
    error_code = "authentication_error"
    http_status_code = 401


class AuthorizationError(AgentepqrError):
    """
    Raised when the caller is authenticated but does not have access.
    """

    default_message = "You are not authorized to perform this action."
    error_code = "authorization_error"
    http_status_code = 403


class ExternalServiceError(AgentepqrError):
    """
    Raised when an external dependency fails or returns an unexpected result.
    """

    default_message = "An external service failed to complete the request."
    error_code = "external_service_error"
    http_status_code = 502


class AgentExecutionError(AgentepqrError):
    """
    Raised when the agent cannot complete its execution successfully.
    """

    default_message = "The agent failed while processing the request."
    error_code = "agent_execution_error"
    http_status_code = 500


class ContextStorageError(AgentepqrError):
    """
    Raised when conversation context cannot be stored, loaded, or serialized.
    """

    default_message = "Conversation context could not be persisted or recovered."
    error_code = "context_storage_error"
    http_status_code = 500
