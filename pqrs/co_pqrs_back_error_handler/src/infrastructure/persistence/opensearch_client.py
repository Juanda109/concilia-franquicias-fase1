"""Minimal OpenSearch HTTP client."""

from __future__ import annotations

from typing import Any

import httpx

from infrastructure.core.config import OpenSearchSettings
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.entrypoint.api.errors.exceptions import ExternalServiceError

logger = get_logger(__name__)


class OpenSearchClient:
    """Thin wrapper around the OpenSearch APIs used by the service."""

    def __init__(self, settings: OpenSearchSettings) -> None:
        self.settings = settings
        self.base_url = settings.endpoint.rstrip("/")
        self.auth = (settings.user, settings.password)
        self._client = httpx.Client(
            verify=settings.verify_ssl,
            auth=self.auth,
            timeout=settings.timeout,
            headers={"Content-Type": "application/json"},
        )

    @log_execution
    def get_document(self, index_name: str, document_id: str) -> dict[str, Any] | None:
        """Return one document or `None` if it does not exist."""

        response = self._request(
            "GET",
            f"/{index_name}/_doc/{document_id}",
            expected_statuses={200, 404},
        )
        if response.status_code == 404:
            return None

        payload = response.json()
        if not payload.get("found", False):
            return None
        return payload.get("_source")

    @log_execution
    def search_by_term(
        self,
        index_name: str,
        field_name: str,
        value: str,
        *,
        size: int = 1000,
        sort: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Search documents matching an exact term query."""

        body: dict[str, Any] = {
            "size": size,
            "query": {
                "term": {
                    field_name: value,
                }
            },
        }
        if sort:
            body["sort"] = sort

        response = self._request(
            "POST",
            f"/{index_name}/_search",
            json=body,
            expected_statuses={200},
        )
        payload = response.json()
        hits = payload.get("hits", {}).get("hits", [])
        return [hit.get("_source", {}) for hit in hits]

    @log_execution
    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        expected_statuses: set[int],
    ) -> httpx.Response:
        url = f"{self.base_url}{path}"
        logger.info("Executing OpenSearch request method=%s url=%s", method, url)

        try:
            response = self._client.request(method, url, json=json)
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "OpenSearch request failed.",
                details={"method": method, "url": url, "reason": repr(exc)},
            ) from exc

        if response.status_code not in expected_statuses:
            raise ExternalServiceError(
                "OpenSearch returned an unexpected response.",
                details={
                    "method": method,
                    "url": url,
                    "status_code": response.status_code,
                    "response": response.text[:1000],
                },
            )

        return response
