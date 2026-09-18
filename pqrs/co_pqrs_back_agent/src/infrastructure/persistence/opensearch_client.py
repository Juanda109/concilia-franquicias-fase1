"""Small OpenSearch HTTP client used by the conversation store."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

import httpx

from infrastructure.core.config import OpenSearchSettings, load_env_constants
from infrastructure.core.logger import get_logger, log_execution
from infrastructure.entrypoint.api.errors.exceptions import ContextStorageError

logger = get_logger(__name__)


class OpenSearchClient:
    """Minimal HTTP wrapper for the OpenSearch APIs used by the project."""

    _memory_indices: dict[str, dict[str, dict[str, Any]]] = {}

    def __init__(self, settings: OpenSearchSettings) -> None:
        self.settings = settings
        self.base_url = self.settings.endpoint.rstrip("/")
        self.auth = (self.settings.user, self.settings.password)
        constants = load_env_constants()
        self.enabled = _parse_bool_env(
            constants.get("OPENSEARCH_ENABLED"),
            default=True,
        )
        self._client = httpx.AsyncClient(
            verify=self.settings.verify_ssl,
            auth=self.auth,
            timeout=self.settings.timeout,
            headers={"Content-Type": "application/json"},
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )
        self._semaphore = asyncio.Semaphore(15)
        logger.info(
            "OpenSearchClient initialized endpoint=%s conversations_index=%s messages_index=%s verify_ssl=%s",
            self.base_url,
            self.settings.conversations_index,
            self.settings.messages_index,
            self.settings.verify_ssl,
        )
        if not self.enabled:
            logger.warning(
                "OpenSearch disabled by OPENSEARCH_ENABLED=false; using in-memory store for local execution"
            )

    @log_execution
    async def get_document(
        self, index_name: str, document_id: str
    ) -> dict[str, Any] | None:
        """Return a single document from an index or `None` if it does not exist."""

        if not self.enabled:
            index = self._memory_indices.get(index_name, {})
            document = index.get(document_id)
            return deepcopy(document) if document is not None else None

        response = await self._request(
            "GET",
            f"/{index_name}/_doc/{document_id}",
            expected_statuses={200, 404},
        )

        if response.status_code == 404:
            return None

        payload = response.json()
        if not payload.get("found", False):
            return None

        return payload["_source"]

    @log_execution
    async def index_document(
        self,
        index_name: str,
        document_id: str,
        document: dict[str, Any],
    ) -> None:
        """Create or replace a single document."""

        if not self.enabled:
            index = self._memory_indices.setdefault(index_name, {})
            index[document_id] = deepcopy(document)
            return

        await self._request(
            "PUT",
            f"/{index_name}/_doc/{document_id}",
            json=document,
            expected_statuses={200, 201},
        )

    @log_execution
    async def update_document(
        self,
        index_name: str,
        document_id: str,
        document: dict[str, Any],
        *,
        upsert: bool = True,
    ) -> None:
        """Partially update a single document with optional upsert behavior."""

        if not self.enabled:
            index = self._memory_indices.setdefault(index_name, {})
            existing = index.get(document_id, {})
            if upsert or existing:
                merged = {
                    **deepcopy(existing),
                    **deepcopy(document),
                }
                index[document_id] = merged
            return

        body: dict[str, Any] = {"doc": document}

        if upsert:
            body["doc_as_upsert"] = True

        await self._request(
            "POST",
            f"/{index_name}/_update/{document_id}",
            json=body,
            expected_statuses={200, 201},
        )

    @log_execution
    async def delete_by_term(
        self, index_name: str, field_name: str, value: str
    ) -> None:
        """Delete documents that match a term query."""

        if not self.enabled:
            index = self._memory_indices.setdefault(index_name, {})
            to_remove = [
                doc_id
                for doc_id, payload in index.items()
                if str(payload.get(field_name)) == value
            ]
            for doc_id in to_remove:
                index.pop(doc_id, None)
            return

        await self._request(
            "POST",
            f"/{index_name}/_delete_by_query",
            json={
                "query": {
                    "term": {
                        field_name: value,
                    }
                }
            },
            expected_statuses={200},
        )

    @log_execution
    async def search_by_term(
        self,
        index_name: str,
        field_name: str,
        value: str,
        *,
        size: int = 1000,
        sort: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Search documents in an index by exact term."""

        if not self.enabled:
            index = self._memory_indices.setdefault(index_name, {})
            records = [
                deepcopy(payload)
                for payload in index.values()
                if str(payload.get(field_name)) == value
            ]
            return records[:size]

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

        response = await self._request(
            "POST",
            f"/{index_name}/_search",
            json=body,
            expected_statuses={200},
        )
        payload = response.json()
        hits = payload.get("hits", {}).get("hits", [])
        return [hit["_source"] for hit in hits]

    @log_execution
    async def refresh_index(self, index_name: str) -> None:
        """Refresh an index so recent writes become visible immediately."""

        if not self.enabled:
            return

        await self._request(
            "POST",
            f"/{index_name}/_refresh",
            expected_statuses={200},
        )

    @log_execution
    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        expected_statuses: set[int],
    ) -> httpx.Response:
        """Execute an HTTP request against OpenSearch and validate the response."""

        url = f"{self.base_url}{path}"
        logger.info("Executing OpenSearch request method=%s url=%s", method, url)

        async with self._semaphore:
            try:
                response = await self._client.request(method, url, json=json)
            except httpx.ConnectError:
                logger.warning(
                    "ConnectError on first attempt, retrying method=%s url=%s",
                    method,
                    url,
                )
                await asyncio.sleep(0.5)
                try:
                    response = await self._client.request(method, url, json=json)
                except httpx.HTTPError as exc:
                    raise ContextStorageError(
                        "OpenSearch request failed.",
                        details={
                            "method": method,
                            "url": url,
                            "reason": repr(exc),
                        },
                    ) from exc
            except httpx.HTTPError as exc:
                raise ContextStorageError(
                    "OpenSearch request failed.",
                    details={
                        "method": method,
                        "url": url,
                        "reason": repr(exc),
                    },
                ) from exc

        if response.status_code not in expected_statuses:
            raise ContextStorageError(
                "OpenSearch returned an unexpected response.",
                details={
                    "method": method,
                    "url": url,
                    "status_code": response.status_code,
                    "response": response.text[:1000],
                },
            )

        return response


def _parse_bool_env(value: str | None, *, default: bool) -> bool:
    """Parse boolean-like values from environment variables."""

    if value is None:
        return default

    normalized = value.strip().casefold()
    if not normalized:
        return default

    return normalized in {"1", "true", "yes", "on"}
