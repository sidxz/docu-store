"""Kafka adapter for publishing integration events."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import structlog
from confluent_kafka import Producer

from infrastructure.config import settings

logger = structlog.get_logger()


class KafkaPublisher:
    """Publisher for integration events using Kafka."""

    def __init__(self) -> None:
        self._producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
        self._topic = settings.kafka_topic
        self._poll_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    async def connect(self) -> None:
        """Start background polling for delivery callbacks."""
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._stop_event.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            name="kafka-producer-poll",
            daemon=True,
        )
        self._poll_thread.start()
        logger.info("kafka_producer_started")

    async def disconnect(self) -> None:
        """Stop background polling and flush pending messages."""
        self._stop_event.set()
        if self._poll_thread:
            self._poll_thread.join(timeout=5)
        await asyncio.to_thread(self._producer.flush, 5)
        logger.info("kafka_producer_stopped")

    async def publish(self, subject: str, event: dict[str, Any]) -> None:
        """Publish an integration event to Kafka."""
        try:
            await self.connect()

            payload = json.dumps(event).encode()
            loop = asyncio.get_running_loop()
            future: asyncio.Future[None] = loop.create_future()

            def delivery(err: Exception | None, msg: Any) -> None:
                if err:
                    logger.error("kafka_publish_failed", subject=subject, error=str(err))
                    loop.call_soon_threadsafe(future.set_exception, err)
                    return
                logger.info(
                    "kafka_event_published",
                    subject=subject,
                    topic=msg.topic(),
                    partition=msg.partition(),
                    offset=msg.offset(),
                )
                loop.call_soon_threadsafe(future.set_result, None)

            self._producer.produce(
                self._topic,
                key=subject,
                value=payload,
                on_delivery=delivery,
            )
            await future
        except Exception as exc:
            logger.error("kafka_publish_exception", subject=subject, error=str(exc))
            raise

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            self._producer.poll(0.1)
