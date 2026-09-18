from __future__ import annotations

from typing import Any, Iterator

from opensearchpy import OpenSearch

from classes.models import Settings
from commons.logging_utils import get_logger


logger = get_logger(__name__)


def build_client(settings: Settings) -> OpenSearch:
    return OpenSearch(
        hosts=settings.hosts,
        http_auth=settings.http_auth,
        verify_certs=settings.verify_certs,
        ssl_show_warn=not settings.verify_certs,
        timeout=settings.timeout_seconds,
        http_compress=True,
    )


def log_connection_help(settings: Settings) -> None:
    configured_hosts = ", ".join(
        f"{'https' if host.get('use_ssl') else 'http'}://{host.get('host')}:{host.get('port')}"
        for host in settings.hosts
    )
    host_names = {str(host.get("host", "")).strip().lower() for host in settings.hosts}

    if host_names and host_names.issubset({"localhost", "127.0.0.1"}):
        logger.error(
            "OpenSearch is configured as %s. Inside the container, 'localhost' points to the container itself. If OpenSearch runs on your machine, set OPENSEARCH_HOSTS to https://host.containers.internal:9200 or to the real reachable DNS/IP of your cluster.",
            configured_hosts,
        )
        return

    logger.error(
        "Could not connect to OpenSearch at %s. Check the host, port, protocol and network reachability.",
        configured_hosts,
    )


def scroll_documents(
    client: OpenSearch,
    settings: Settings,
    index: str,
    query: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    response = client.search(
        index=index,
        body={"query": query, "sort": ["_doc"]},
        size=settings.batch_size,
        scroll=settings.scroll_keepalive,
    )
    scroll_id = response.get("_scroll_id")

    try:
        while True:
            hits = response.get("hits", {}).get("hits", [])
            if not hits:
                break

            for hit in hits:
                yield hit

            if not scroll_id:
                break

            response = client.scroll(
                scroll_id=scroll_id,
                scroll=settings.scroll_keepalive,
            )
            scroll_id = response.get("_scroll_id", scroll_id)
    finally:
        if scroll_id:
            try:
                client.clear_scroll(scroll_id=scroll_id)
            except Exception:
                logger.debug("Unable to clear scroll %s", scroll_id, exc_info=True)


def count_documents(
    client: OpenSearch,
    index: str,
    query: dict[str, Any],
) -> int:
    response = client.count(
        index=index,
        body={"query": query},
    )
    return int(response.get("count", 0))


def build_status_match_query(field_name: str, value: str) -> dict[str, Any]:
    if field_name.endswith(".keyword"):
        return {"term": {field_name: value}}

    return {
        "bool": {
            "should": [
                {"term": {field_name: value}},
                {"term": {f"{field_name}.keyword": value}},
                {"match_phrase": {field_name: value}},
            ],
            "minimum_should_match": 1,
        }
    }


def build_exact_match_query(field_name: str, value: str) -> dict[str, Any]:
    if field_name.endswith(".keyword"):
        return {"term": {field_name: value}}

    return {
        "bool": {
            "should": [
                {"term": {field_name: value}},
                {"term": {f"{field_name}.keyword": value}},
            ],
            "minimum_should_match": 1,
        }
    }


def build_closed_conversations_query(settings: Settings) -> dict[str, Any]:
    query: dict[str, Any] = {
        "bool": {
            "must": [
                build_status_match_query(
                    settings.conversation_status_field,
                    settings.closed_status_value,
                )
            ]
        }
    }

    if not settings.delete_exported_conversations:
        query["bool"]["must_not"] = [{"exists": {"field": settings.exported_at_field}}]

    return query
