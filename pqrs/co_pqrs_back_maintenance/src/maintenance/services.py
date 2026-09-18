from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError

from classes.models import (
    ArchiveConversationResult,
    CloseSummary,
    ExportSummary,
    Settings,
)
from commons.datetime_utils import extract_first_datetime, get_field, parse_datetime
from commons.logging_utils import get_logger, log_execution
from commons.object_store import ObjectStore
from commons.opensearch_helpers import (
    build_closed_conversations_query,
    build_exact_match_query,
    build_status_match_query,
    count_documents,
    scroll_documents,
)
from commons.path_utils import sanitize_path_component


logger = get_logger(__name__)

ARCHIVE_STATUS_ARCHIVED = "archived"
ARCHIVE_STATUS_ALREADY_EXPORTED = "already_exported"
ARCHIVE_STATUS_ALREADY_PROCESSING = "already_processing"
ARCHIVE_STATUS_NOT_CLOSED = "not_closed"
ARCHIVE_STATUS_NOT_FOUND = "not_found"
ARCHIVE_STATUS_AMBIGUOUS = "ambiguous"
CLAIM_CONFLICT_ATTEMPTS = 3


@dataclass(frozen=True)
class ClaimedConversation:
    hit: dict[str, Any]
    conversation_id: str
    closed_at: datetime
    relative_path: Path
    lock_owner: str


@log_execution
def export_closed_conversations(
    client: OpenSearch,
    settings: Settings,
    now: datetime,
) -> ExportSummary:
    query = build_closed_conversations_query(settings)
    candidates = count_documents(client, settings.conversations_index, query)
    logger.info(
        "Closed conversation candidates found=%s status_field=%s closed_value=%s",
        candidates,
        settings.conversation_status_field,
        settings.closed_status_value,
    )

    exported = 0
    deleted_conversations = 0
    deleted_messages_total = 0
    marked_as_exported = 0

    for hit in scroll_documents(client, settings, settings.conversations_index, query):
        result = archive_conversation_document(
            client=client,
            settings=settings,
            document_id=str(hit["_id"]),
            now=now,
            trigger="cron",
            expected_conversation_id=get_conversation_id(settings, hit),
        )

        if result.status == ARCHIVE_STATUS_ARCHIVED:
            exported += 1
            deleted_conversations += int(result.deleted_conversation)
            deleted_messages_total += result.deleted_messages
            marked_as_exported += int(result.marked_as_exported)
            continue

        logger.info(
            "Skipped closed conversation status=%s conversation_id=%s document_id=%s detail=%s",
            result.status,
            result.conversation_id,
            result.document_id or hit["_id"],
            result.detail,
        )

    return ExportSummary(
        candidates_found=candidates,
        exported_conversations=exported,
        deleted_conversations=deleted_conversations,
        deleted_messages=deleted_messages_total,
        marked_as_exported=marked_as_exported,
    )


@log_execution
def archive_conversation_by_id(
    client: OpenSearch,
    settings: Settings,
    conversation_id: str,
    now: datetime,
) -> ArchiveConversationResult:
    last_result = build_archive_result(
        status=ARCHIVE_STATUS_NOT_FOUND,
        conversation_id=conversation_id,
        document_id=None,
        detail="conversation_not_found",
    )

    for attempt in range(settings.archive_lookup_retries + 1):
        lookup = find_conversation_document_id(
            client=client,
            settings=settings,
            conversation_id=conversation_id,
        )

        if isinstance(lookup, ArchiveConversationResult):
            last_result = lookup
        else:
            last_result = archive_conversation_document(
                client=client,
                settings=settings,
                document_id=lookup,
                now=now,
                trigger="api",
                expected_conversation_id=conversation_id,
            )

        if last_result.status not in {ARCHIVE_STATUS_NOT_FOUND, ARCHIVE_STATUS_NOT_CLOSED}:
            return last_result

        if attempt == settings.archive_lookup_retries:
            return last_result

        time.sleep(settings.archive_lookup_retry_seconds)

    return last_result


@log_execution
def close_stale_active_conversations(
    client: OpenSearch,
    settings: Settings,
    now: datetime,
) -> CloseSummary:
    query = {
        "bool": {
            "must": [build_status_match_query(settings.conversation_status_field, settings.active_status_value)],
        }
    }
    candidates = count_documents(client, settings.conversations_index, query)
    logger.info(
        "Active conversation candidates found=%s status_field=%s active_value=%s",
        candidates,
        settings.conversation_status_field,
        settings.active_status_value,
    )

    closed = 0
    skipped_missing_last_interaction = 0
    inactivity_window = timedelta(minutes=settings.inactive_minutes)

    for hit in scroll_documents(client, settings, settings.conversations_index, query):
        source = hit.get("_source", {})
        last_interaction = extract_first_datetime(
            source,
            settings.last_interaction_fields,
            settings.default_timezone,
        )

        if last_interaction is None:
            skipped_missing_last_interaction += 1
            logger.warning(
                "Skipping active conversation conversation_id=%s because no last interaction field was found in %s",
                get_conversation_id(settings, hit),
                settings.last_interaction_fields,
            )
            continue

        if now - last_interaction < inactivity_window:
            continue

        satisfaction_status, satisfaction_result = resolve_satisfaction_fields(
            source,
            is_closed=True,
        )

        client.update(
            index=settings.conversations_index,
            id=hit["_id"],
            body={
                "doc": {
                    get_writable_field_name(settings.conversation_status_field): settings.closed_status_value,
                    get_writable_field_name(settings.closed_at_field): now.isoformat(),
                    "satisfaction_status": satisfaction_status,
                    "satisfaction_result": satisfaction_result,
                }
            },
            refresh="wait_for",
            retry_on_conflict=3,
        )

        closed += 1
        logger.info(
            "Marked conversation as closed conversation_id=%s inactive_minutes=%s last_interaction=%s closed_at=%s",
            get_conversation_id(settings, hit),
            settings.inactive_minutes,
            last_interaction.isoformat(),
            now.isoformat(),
        )

    return CloseSummary(
        candidates_found=candidates,
        closed_from_active=closed,
        skipped_missing_last_interaction=skipped_missing_last_interaction,
    )


def archive_conversation_document(
    client: OpenSearch,
    settings: Settings,
    document_id: str,
    now: datetime,
    trigger: str,
    expected_conversation_id: str | None = None,
) -> ArchiveConversationResult:
    lock_owner = build_lock_owner(trigger)
    claimed = claim_conversation_for_archival(
        client=client,
        settings=settings,
        document_id=document_id,
        now=now,
        lock_owner=lock_owner,
        expected_conversation_id=expected_conversation_id,
    )

    if isinstance(claimed, ArchiveConversationResult):
        return claimed

    try:
        source = claimed.hit.get("_source", {})
        satisfaction_status, satisfaction_result = resolve_satisfaction_fields(source, is_closed=True)
        source["satisfaction_status"] = satisfaction_status
        source["satisfaction_result"] = satisfaction_result

        messages = fetch_messages(client, settings, claimed.conversation_id)
        payload, relative_path = build_export_payload(
            hit=claimed.hit,
            conversation_id=claimed.conversation_id,
            messages=messages,
            closed_at=claimed.closed_at,
            exported_at=now,
            output_dir=settings.output_dir,
            existing_relative_path=claimed.relative_path.as_posix(),
        )
        write_export(settings, relative_path, payload)

        deleted_messages = 0
        if settings.delete_exported_messages:
            deleted_messages = delete_exported_messages(client, messages)

        deleted_conversation = False
        marked_as_exported = False

        if settings.delete_exported_conversations:
            deleted_conversation = delete_exported_conversation(client, settings, claimed.hit["_id"])
        else:
            mark_conversation_as_exported(
                client=client,
                settings=settings,
                document_id=claimed.hit["_id"],
                exported_at=now,
                relative_path=relative_path.as_posix(),
                satisfaction_status=satisfaction_status,
                satisfaction_result=satisfaction_result,
            )
            marked_as_exported = True

        logger.info(
            "Archived conversation trigger=%s conversation_id=%s document_id=%s message_count=%s export_path=%s deleted_messages=%s deleted_conversation=%s marked_as_exported=%s",
            trigger,
            claimed.conversation_id,
            claimed.hit["_id"],
            len(messages),
            relative_path.as_posix(),
            deleted_messages,
            deleted_conversation,
            marked_as_exported,
        )

        return build_archive_result(
            status=ARCHIVE_STATUS_ARCHIVED,
            conversation_id=claimed.conversation_id,
            document_id=claimed.hit["_id"],
            export_relative_path=relative_path.as_posix(),
            message_count=len(messages),
            deleted_messages=deleted_messages,
            deleted_conversation=deleted_conversation,
            marked_as_exported=marked_as_exported,
        )
    except Exception:
        release_conversation_claim(
            client=client,
            settings=settings,
            document_id=claimed.hit["_id"],
            lock_owner=claimed.lock_owner,
        )
        raise


def claim_conversation_for_archival(
    client: OpenSearch,
    settings: Settings,
    document_id: str,
    now: datetime,
    lock_owner: str,
    expected_conversation_id: str | None = None,
) -> ClaimedConversation | ArchiveConversationResult:
    last_result: ArchiveConversationResult | None = None

    for _ in range(CLAIM_CONFLICT_ATTEMPTS):
        try:
            hit = load_conversation_hit(client, settings, document_id)
        except NotFoundError:
            return build_missing_result(settings, expected_conversation_id, document_id)

        source = hit.get("_source", {})
        conversation_id = get_conversation_id(settings, hit)

        if not is_closed_conversation(source, settings):
            last_result = build_archive_result(
                status=ARCHIVE_STATUS_NOT_CLOSED,
                conversation_id=conversation_id,
                document_id=document_id,
                export_relative_path=get_source_field(source, settings.exported_path_field),
                detail="conversation_is_not_closed",
            )
            break

        if is_conversation_already_exported(source, settings):
            return build_archive_result(
                status=ARCHIVE_STATUS_ALREADY_EXPORTED,
                conversation_id=conversation_id,
                document_id=document_id,
                export_relative_path=get_source_field(source, settings.exported_path_field),
                detail="conversation_already_exported",
            )

        if is_processing_lock_active(source, settings, now):
            return build_archive_result(
                status=ARCHIVE_STATUS_ALREADY_PROCESSING,
                conversation_id=conversation_id,
                document_id=document_id,
                export_relative_path=get_source_field(source, settings.exported_path_field),
                detail="conversation_is_currently_claimed",
            )

        closed_at = resolve_closed_at(source, settings, now)
        relative_path = resolve_export_relative_path(
            conversation_id=conversation_id,
            closed_at=closed_at,
            existing_relative_path=get_source_field(source, settings.exported_path_field),
        )
        update_doc = {
            get_writable_field_name(settings.locked_at_field): now.isoformat(),
            get_writable_field_name(settings.locked_by_field): lock_owner,
            get_writable_field_name(settings.exported_path_field): relative_path.as_posix(),
        }

        if get_source_field(source, settings.closed_at_field) is None:
            update_doc[get_writable_field_name(settings.closed_at_field)] = closed_at.isoformat()

        try:
            client.update(
                index=settings.conversations_index,
                id=document_id,
                body={"doc": update_doc},
                if_seq_no=hit["_seq_no"],
                if_primary_term=hit["_primary_term"],
                retry_on_conflict=0,
            )
        except NotFoundError:
            return build_missing_result(settings, conversation_id, document_id)
        except Exception as exc:
            if getattr(exc, "status_code", None) == 409:
                continue
            raise

        claimed_source = dict(source)
        claimed_source.update(update_doc)
        claimed_hit = dict(hit)
        claimed_hit["_source"] = claimed_source
        return ClaimedConversation(
            hit=claimed_hit,
            conversation_id=conversation_id,
            closed_at=closed_at,
            relative_path=relative_path,
            lock_owner=lock_owner,
        )

    return last_result or build_archive_result(
        status=ARCHIVE_STATUS_ALREADY_PROCESSING,
        conversation_id=expected_conversation_id,
        document_id=document_id,
        detail="claim_conflict_retry_exhausted",
    )


def find_conversation_document_id(
    client: OpenSearch,
    settings: Settings,
    conversation_id: str,
) -> str | ArchiveConversationResult:
    if settings.conversation_id_field is not None:
        response = client.search(
            index=settings.conversations_index,
            body={
                "query": build_exact_match_query(
                    settings.conversation_id_field,
                    conversation_id,
                )
            },
            size=2,
        )
        hits = response.get("hits", {}).get("hits", [])

        if len(hits) > 1:
            return build_archive_result(
                status=ARCHIVE_STATUS_AMBIGUOUS,
                conversation_id=conversation_id,
                document_id=None,
                detail="multiple_conversations_matched_identifier",
            )

        if hits:
            return str(hits[0]["_id"])

    try:
        hit = load_conversation_hit(client, settings, conversation_id)
        return str(hit["_id"])
    except NotFoundError:
        return build_missing_result(settings, conversation_id, None)


def fetch_messages(
    client: OpenSearch,
    settings: Settings,
    conversation_id: str,
) -> list[dict[str, Any]]:
    query = build_exact_match_query(
        settings.message_conversation_id_field,
        conversation_id,
    )

    hits = list(scroll_documents(client, settings, settings.messages_index, query))
    hits.sort(
        key=lambda hit: extract_first_datetime(
            hit.get("_source", {}),
            settings.message_timestamp_fields,
            settings.default_timezone,
        )
        or datetime.min.replace(tzinfo=UTC)
    )
    return hits


def build_export_payload(
    *,
    hit: dict[str, Any],
    conversation_id: str,
    messages: list[dict[str, Any]],
    closed_at: datetime,
    exported_at: datetime,
    output_dir: Path,
    existing_relative_path: Any,
) -> tuple[dict[str, Any], Path]:
    relative_path = resolve_export_relative_path(
        conversation_id=conversation_id,
        closed_at=closed_at,
        existing_relative_path=existing_relative_path,
    )

    payload = {
        "metadata": {
            "conversation_id": conversation_id,
            "conversation_document_id": hit["_id"],
            "conversation_index": hit["_index"],
            "messages_index": messages[0]["_index"] if messages else None,
            "message_count": len(messages),
            "closed_at": closed_at.isoformat(),
            "exported_at": exported_at.isoformat(),
            "export_relative_path": relative_path.as_posix(),
            "output_root": str(output_dir.resolve()),
        },
        "conversation": {
            "_id": hit["_id"],
            "_index": hit["_index"],
            "_source": hit.get("_source", {}),
        },
        "messages": [
            {
                "_id": message["_id"],
                "_index": message["_index"],
                "_source": message.get("_source", {}),
            }
            for message in messages
        ],
    }

    return payload, relative_path


def write_export_file(
    output_dir: Path,
    relative_path: Path,
    payload: dict[str, Any],
) -> None:
    file_path = output_dir / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if file_path.exists():
        logger.info("Export file already exists, reusing path=%s", relative_path.as_posix())
        return

    temp_path = file_path.with_name(f".{file_path.name}.{uuid4().hex}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if file_path.exists():
        temp_path.unlink(missing_ok=True)
        logger.info("Export file appeared while writing, reusing path=%s", relative_path.as_posix())
        return

    temp_path.replace(file_path)


_object_store: ObjectStore | None = None


def get_object_store(settings: Settings) -> ObjectStore:
    """Return a process-wide ObjectStore instance, building it on first use."""

    global _object_store
    if _object_store is None:
        _object_store = ObjectStore(settings)
    return _object_store


def write_export(
    settings: Settings,
    relative_path: Path,
    payload: dict[str, Any],
    *,
    store: ObjectStore | None = None,
) -> None:
    """Persist the raw export plus a flattened NDJSON summary.

    Switches between the local filesystem and MinIO depending on
    ``settings.minio_enabled``. The raw object preserves the deterministic
    relative path as its key; the summary lands under ``summaries/dt=.../``.
    """

    raw_key = relative_path.as_posix()
    summary = build_conversation_summary(payload)
    summary_key = build_summary_key(summary, payload)

    if settings.minio_enabled:
        active_store = store or get_object_store(settings)
        active_store.write_json(raw_key, payload)
        active_store.write_ndjson(summary_key, [summary])
        logger.info(
            "Exported conversation to MinIO bucket=%s raw_key=%s summary_key=%s",
            active_store.bucket,
            raw_key,
            summary_key,
        )
        return

    write_export_file(settings.output_dir, relative_path, payload)
    write_summary_file(settings.output_dir, summary_key, summary)


def write_summary_file(
    output_dir: Path,
    summary_key: str,
    summary: dict[str, Any],
) -> None:
    """Write the flattened conversation summary to disk (filesystem backend)."""

    file_path = output_dir / summary_key
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if file_path.exists():
        logger.info("Summary file already exists, reusing path=%s", summary_key)
        return

    temp_path = file_path.with_name(f".{file_path.name}.{uuid4().hex}.tmp")
    temp_path.write_text(
        json.dumps(summary, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if file_path.exists():
        temp_path.unlink(missing_ok=True)
        return

    temp_path.replace(file_path)


def build_conversation_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten an export payload into a single analytics-friendly record."""

    metadata = payload.get("metadata", {})
    conversation_source = payload.get("conversation", {}).get("_source", {})
    messages = payload.get("messages", [])

    total_tokens = 0
    total_duration_ms = 0
    for message in messages:
        source = message.get("_source", {})
        tokens = source.get("tokens") or {}
        timing = source.get("timing") or {}
        total_tokens += _coerce_int(tokens.get("total_tokens"))
        total_duration_ms += _coerce_int(timing.get("total_duration_ms"))

    message_count = metadata.get("message_count")
    if message_count is None:
        message_count = len(messages)

    return {
        "conversation_id": conversation_source.get("conversation_id")
        or metadata.get("conversation_id"),
        "user_id": conversation_source.get("user_id"),
        "status": conversation_source.get("status"),
        "general_workflow": conversation_source.get("general_workflow"),
        "workflow": conversation_source.get("workflow"),
        "final_step": conversation_source.get("current_step"),
        "satisfaction_status": conversation_source.get("satisfaction_status"),
        "satisfaction_result": conversation_source.get("satisfaction_result"),
        "first_msg_date": conversation_source.get("first_msg_date"),
        "last_msg_date": conversation_source.get("last_msg_date"),
        "closed_at": metadata.get("closed_at") or conversation_source.get("closed_at"),
        "exported_at": metadata.get("exported_at"),
        "message_count": message_count,
        "total_tokens": total_tokens,
        "total_duration_ms": total_duration_ms,
    }


def build_summary_key(summary: dict[str, Any], payload: dict[str, Any]) -> str:
    """Build the NDJSON summary object key partitioned by close date."""

    conversation_id = str(
        summary.get("conversation_id")
        or payload.get("metadata", {}).get("conversation_id")
        or "unknown"
    )
    safe_conversation_id = sanitize_path_component(conversation_id)

    closed_at_raw = summary.get("closed_at") or payload.get("metadata", {}).get("closed_at")
    partition = _date_partition(closed_at_raw)

    return f"summaries/dt={partition}/{safe_conversation_id}.json"


def _date_partition(value: Any) -> str:
    parsed = parse_datetime(value, "UTC")
    if parsed is None:
        parsed = datetime.now(UTC)
    return parsed.astimezone(UTC).strftime("%Y-%m-%d")


def _coerce_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def mark_conversation_as_exported(
    client: OpenSearch,
    settings: Settings,
    document_id: str,
    exported_at: datetime,
    relative_path: str,
    satisfaction_status: str | None,
    satisfaction_result: bool | None,
) -> None:
    client.update(
        index=settings.conversations_index,
        id=document_id,
        body={
            "doc": {
                get_writable_field_name(settings.exported_at_field): exported_at.isoformat(),
                get_writable_field_name(settings.exported_path_field): relative_path,
                get_writable_field_name(settings.locked_at_field): None,
                get_writable_field_name(settings.locked_by_field): None,
                "satisfaction_status": satisfaction_status,
                "satisfaction_result": satisfaction_result,
            }
        },
        refresh="wait_for",
        retry_on_conflict=3,
    )


def delete_exported_messages(
    client: OpenSearch,
    messages: list[dict[str, Any]],
) -> int:
    deleted = 0

    for message in messages:
        try:
            client.delete(
                index=message["_index"],
                id=message["_id"],
                refresh="wait_for",
            )
            deleted += 1
        except NotFoundError:
            logger.warning(
                "Message already deleted message_id=%s index=%s",
                message["_id"],
                message["_index"],
            )

    return deleted


def delete_exported_conversation(
    client: OpenSearch,
    settings: Settings,
    document_id: str,
) -> bool:
    try:
        client.delete(
            index=settings.conversations_index,
            id=document_id,
            refresh="wait_for",
        )
        return True
    except NotFoundError:
        logger.warning(
            "Conversation already deleted document_id=%s index=%s",
            document_id,
            settings.conversations_index,
        )
        return False


def release_conversation_claim(
    client: OpenSearch,
    settings: Settings,
    document_id: str,
    lock_owner: str,
) -> None:
    try:
        hit = load_conversation_hit(client, settings, document_id)
    except NotFoundError:
        return

    source = hit.get("_source", {})
    current_lock_owner = get_source_field(source, settings.locked_by_field)

    if current_lock_owner != lock_owner:
        return

    try:
        client.update(
            index=settings.conversations_index,
            id=document_id,
            body={
                "doc": {
                    get_writable_field_name(settings.locked_at_field): None,
                    get_writable_field_name(settings.locked_by_field): None,
                }
            },
            if_seq_no=hit["_seq_no"],
            if_primary_term=hit["_primary_term"],
            retry_on_conflict=0,
        )
    except Exception as exc:
        if getattr(exc, "status_code", None) in {404, 409}:
            return
        raise


def load_conversation_hit(
    client: OpenSearch,
    settings: Settings,
    document_id: str,
) -> dict[str, Any]:
    response = client.get(index=settings.conversations_index, id=document_id)
    return {
        "_id": response["_id"],
        "_index": response["_index"],
        "_source": response.get("_source", {}),
        "_seq_no": response.get("_seq_no"),
        "_primary_term": response.get("_primary_term"),
    }


def resolve_closed_at(
    source: dict[str, Any],
    settings: Settings,
    now: datetime,
) -> datetime:
    return (
        parse_datetime(get_source_field(source, settings.closed_at_field), settings.default_timezone)
        or extract_first_datetime(source, settings.last_interaction_fields, settings.default_timezone)
        or now
    )


def resolve_export_relative_path(
    conversation_id: str,
    closed_at: datetime,
    existing_relative_path: Any,
) -> Path:
    if isinstance(existing_relative_path, str) and existing_relative_path.strip():
        return Path(existing_relative_path.strip())

    timestamp = closed_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_conversation_id = sanitize_path_component(conversation_id)
    return (
        Path("conversations")
        / safe_conversation_id
        / closed_at.strftime("%Y")
        / closed_at.strftime("%m")
        / closed_at.strftime("%d")
        / f"{safe_conversation_id}_{timestamp}.json"
    )


def is_processing_lock_active(
    source: dict[str, Any],
    settings: Settings,
    now: datetime,
) -> bool:
    locked_at = parse_datetime(
        get_source_field(source, settings.locked_at_field),
        settings.default_timezone,
    )

    if locked_at is None:
        return False

    return now - locked_at < timedelta(seconds=settings.lock_timeout_seconds)


def is_closed_conversation(
    source: dict[str, Any],
    settings: Settings,
) -> bool:
    current_status = get_source_field(source, settings.conversation_status_field)
    return current_status == settings.closed_status_value


def is_conversation_already_exported(
    source: dict[str, Any],
    settings: Settings,
) -> bool:
    if settings.delete_exported_conversations:
        return False

    return get_source_field(source, settings.exported_at_field) is not None


def find_existing_export_relative_path(
    output_dir: Path,
    conversation_id: str,
) -> str | None:
    conversation_root = output_dir / "conversations" / sanitize_path_component(conversation_id)
    if not conversation_root.exists():
        return None

    files = sorted(conversation_root.rglob("*.json"))
    if not files:
        return None

    return files[0].relative_to(output_dir).as_posix()


def build_missing_result(
    settings: Settings,
    conversation_id: str | None,
    document_id: str | None,
) -> ArchiveConversationResult:
    if conversation_id:
        export_relative_path = find_existing_export_relative_path(settings.output_dir, conversation_id)
        if export_relative_path is not None:
            return build_archive_result(
                status=ARCHIVE_STATUS_ALREADY_EXPORTED,
                conversation_id=conversation_id,
                document_id=document_id,
                export_relative_path=export_relative_path,
                detail="conversation_already_archived_to_disk",
            )

    return build_archive_result(
        status=ARCHIVE_STATUS_NOT_FOUND,
        conversation_id=conversation_id,
        document_id=document_id,
        detail="conversation_not_found",
    )


def build_archive_result(
    *,
    status: str,
    conversation_id: str | None,
    document_id: str | None,
    export_relative_path: str | None = None,
    message_count: int = 0,
    deleted_messages: int = 0,
    deleted_conversation: bool = False,
    marked_as_exported: bool = False,
    detail: str | None = None,
) -> ArchiveConversationResult:
    return ArchiveConversationResult(
        status=status,
        conversation_id=conversation_id,
        document_id=document_id,
        export_relative_path=export_relative_path,
        message_count=message_count,
        deleted_messages=deleted_messages,
        deleted_conversation=deleted_conversation,
        marked_as_exported=marked_as_exported,
        detail=detail,
    )


def build_lock_owner(trigger: str) -> str:
    hostname = socket.gethostname()
    return f"{trigger}:{hostname}:{uuid4().hex}"


def get_conversation_id(settings: Settings, hit: dict[str, Any]) -> str:
    source = hit.get("_source", {})
    if settings.conversation_id_field:
        candidate = get_source_field(source, settings.conversation_id_field)
        if candidate is not None:
            return str(candidate)
    return str(hit["_id"])


def get_source_field(payload: dict[str, Any], field_name: str) -> Any:
    value = get_field(payload, field_name)
    if value is not None:
        return value

    if field_name.endswith(".keyword"):
        return get_field(payload, field_name[:-8])

    return None


def get_writable_field_name(field_name: str) -> str:
    if field_name.endswith(".keyword"):
        return field_name[:-8]
    return field_name


def resolve_satisfaction_fields(
    source: dict[str, Any],
    *,
    is_closed: bool,
) -> tuple[str | None, bool | None]:
    existing_status = normalize_satisfaction_status(get_source_field(source, "satisfaction_status"))
    existing_result = normalize_satisfaction_result(get_source_field(source, "satisfaction_result"))

    inferred_result = infer_satisfaction_result(source)
    satisfaction_result = existing_result if existing_result is not None else inferred_result

    if satisfaction_result is not None:
        return "ENTERED", satisfaction_result

    if is_closed:
        return "ABANDONED", None

    return existing_status, None


def infer_satisfaction_result(source: dict[str, Any]) -> bool | None:
    current_step = str(get_source_field(source, "current_step") or "").lower().strip()
    if current_step == "satisfaction_si":
        return True
    if current_step == "satisfaction_no":
        return False

    flow_answers = get_source_field(source, "flow_answers")
    if isinstance(flow_answers, dict):
        flow_value = (
            flow_answers.get("satisfaccion_respuesta")
            or flow_answers.get("satisfaction_response")
            or flow_answers.get("satisfaction_result")
        )
        return normalize_satisfaction_result(flow_value)

    return None


def normalize_satisfaction_status(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in {"ENTERED", "ABANDONED"}:
            return normalized

    return None


def normalize_satisfaction_result(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value

    if value is None:
        return None

    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "si", "sí", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False

    return None
