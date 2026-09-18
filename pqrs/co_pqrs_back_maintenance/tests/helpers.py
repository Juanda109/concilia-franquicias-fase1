from __future__ import annotations

from pathlib import Path

from classes.models import Settings


def make_settings(**overrides) -> Settings:
    """Build a Settings instance with sensible defaults for tests."""

    base = dict(
        hosts=[{"host": "opensearch", "port": 9200, "use_ssl": True}],
        http_auth=("admin", "secret"),
        verify_certs=False,
        timeout_seconds=30,
        default_timezone="UTC",
        conversations_index="conversations-reference",
        messages_index="conversations-messages",
        output_dir=Path("./output"),
        batch_size=250,
        scroll_keepalive="2m",
        inactive_minutes=5,
        conversation_status_field="status",
        active_status_value="Active",
        closed_status_value="Closed",
        conversation_id_field="id",
        message_conversation_id_field="conversation_id",
        last_interaction_fields=["last_msg_date"],
        message_timestamp_fields=["created_at"],
        closed_at_field="closed_at",
        exported_at_field="maintenance_exported_at",
        exported_path_field="maintenance_export_path",
        locked_at_field="maintenance_locked_at",
        locked_by_field="maintenance_locked_by",
        lock_timeout_seconds=300,
        archive_lookup_retries=3,
        archive_lookup_retry_seconds=1,
        api_token=None,
        delete_exported_conversations=True,
        delete_exported_messages=True,
        minio_enabled=True,
        minio_endpoint_url="http://minio:9000",
        minio_bucket="pqr-conversations-history",
        minio_region="us-east-1",
        minio_access_key="admin",
        minio_secret_key="topsecret",
        minio_addressing_style="path",
        control_index="client-control-table",
        error_handler_service_url=None,
    )
    base.update(overrides)
    return Settings(**base)
