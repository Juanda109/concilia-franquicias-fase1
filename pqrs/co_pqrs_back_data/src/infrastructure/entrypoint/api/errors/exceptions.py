"""Application exceptions translated by the API layer."""

from typing import Any

from fastapi import status


class BackDataError(Exception):
    """Base error for expected application failures."""

    error_code = "back_data_error"
    http_status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details,
            }
        }


class CustomerNotFoundError(BackDataError):
    """Raised when the requested customer id does not exist in the CSV."""

    error_code = "customer_not_found"
    http_status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, customer_id: str) -> None:
        super().__init__(
            "Customer data was not found.",
            details={"customer_id": customer_id},
        )


class DataSourceError(BackDataError):
    """Raised when the configured data source cannot be read."""

    error_code = "data_source_error"
    http_status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

