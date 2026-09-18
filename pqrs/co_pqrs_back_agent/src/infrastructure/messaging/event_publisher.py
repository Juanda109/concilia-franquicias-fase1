"""Fire-and-forget RabbitMQ event publisher for real-time analytics.

The agent publishes conversation lifecycle events to a durable topic exchange
(``pqr.events``) so a downstream pipeline (Logstash -> Elasticsearch -> Kibana)
can build a real-time dashboard. Publishing is best-effort and must NEVER affect
the conversation or its latency:

- it is gated by ``RabbitMQSettings.enabled`` (inert until switched on),
- every publish swallows all errors after logging,
- a lazy ``connect_robust`` connection auto-reconnects,
- callers schedule ``publish`` as a detached task (never awaited inline).

``aio_pika`` is imported lazily so this module can be imported (and tested)
without the dependency installed.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from infrastructure.core.config import RabbitMQSettings
from infrastructure.core.logger import get_logger

logger = get_logger(__name__)


class EventPublisher:
    """Publish JSON events to a durable RabbitMQ topic exchange."""

    def __init__(self, settings: RabbitMQSettings) -> None:
        self._settings = settings
        self._lock = asyncio.Lock()
        self._connection: Any | None = None
        self._channel: Any | None = None
        self._exchange: Any | None = None

    async def _ensure_exchange(self) -> Any:
        """Lazily establish the robust connection, channel and exchange."""

        if self._exchange is not None:
            return self._exchange

        async with self._lock:
            if self._exchange is not None:
                return self._exchange

            import aio_pika

            self._connection = await aio_pika.connect_robust(
                self._settings.effective_url()
            )
            self._channel = await self._connection.channel(publisher_confirms=False)
            self._exchange = await self._channel.declare_exchange(
                self._settings.exchange,
                aio_pika.ExchangeType(self._settings.exchange_type),
                durable=True,
            )
            logger.info(
                "RabbitMQ exchange ready exchange=%s type=%s",
                self._settings.exchange,
                self._settings.exchange_type,
            )
            return self._exchange

    async def publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        """Publish one persistent JSON event. Never raises."""

        try:
            import aio_pika

            exchange = await self._ensure_exchange()
            message = aio_pika.Message(
                body=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
            )
            await asyncio.wait_for(
                exchange.publish(message, routing_key=routing_key),
                timeout=self._settings.publish_timeout_seconds,
            )
            logger.info("Published event routing_key=%s", routing_key)
        except Exception:
            logger.exception(
                "Failed to publish event routing_key=%s; resetting connection",
                routing_key,
            )
            await self._reset()

    async def _reset(self) -> None:
        """Drop the cached connection so the next publish reconnects."""

        connection = self._connection
        self._exchange = None
        self._channel = None
        self._connection = None
        if connection is not None:
            try:
                await connection.close()
            except Exception:
                logger.debug("Error while closing RabbitMQ connection", exc_info=True)

    async def close(self) -> None:
        """Close the underlying connection (used on shutdown)."""

        await self._reset()
