"""Plugin consumer — Kafka consumer that routes events to plugin handlers.

This is the single new process that runs all enabled plugins.
It creates per-plugin Kafka consumer groups and starts a shared
Temporal worker for plugin workflows/activities.
"""

from __future__ import annotations

import asyncio
import json
import signal
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from application.plugins.protocol import PluginContext, PluginEventHandler
    from application.plugins.registry import PluginRegistry

logger = structlog.get_logger()


async def run_plugin_consumer(
    registry: PluginRegistry,
    context: PluginContext,
    kafka_bootstrap_servers: str,
    kafka_topic: str,
) -> None:
    """Run the plugin consumer loop.

    Creates a Kafka consumer per enabled plugin (each with its own consumer
    group) and dispatches matching events to plugin handlers.  Plugin failures
    are logged and swallowed — one plugin's error never blocks another.
    """
    if len(registry) == 0:
        logger.info("plugin_consumer.no_plugins")
        return

    routing_table = registry.build_event_routing_table(context)
    all_sub_types = registry.collect_all_subscribed_events()

    logger.info(
        "plugin_consumer.starting",
        plugin_count=len(registry),
        subscribed_events=sorted(all_sub_types),
    )

    consumer, kafka_error_cls = _create_kafka_consumer(kafka_bootstrap_servers, kafka_topic)
    if consumer is None:
        return

    shutdown = asyncio.Event()

    def _signal_handler(signum: int, _frame: object) -> None:
        logger.info("plugin_consumer.signal_received", signum=signum)
        shutdown.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        await _consume_loop(consumer, kafka_error_cls, routing_table, shutdown)
    finally:
        consumer.close()
        logger.info("plugin_consumer.stopped")


def _create_kafka_consumer(
    bootstrap_servers: str,
    topic: str,
) -> tuple[object | None, type | None]:
    """Create and subscribe a Kafka consumer. Returns (consumer, KafkaError) or (None, None)."""
    try:
        from confluent_kafka import Consumer, KafkaError  # noqa: PLC0415
    except ImportError:
        logger.exception("plugin_consumer.confluent_kafka_not_installed")
        return None, None

    consumer_config = {
        "bootstrap.servers": bootstrap_servers,
        "group.id": "plugin_consumer",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": True,
    }

    consumer = Consumer(consumer_config)
    consumer.subscribe([topic])
    return consumer, KafkaError


async def _consume_loop(
    consumer: object,
    kafka_error_cls: type,
    routing_table: dict[str, list[PluginEventHandler]],
    shutdown: asyncio.Event,
) -> None:
    """Poll messages and dispatch to plugin handlers until shutdown."""
    loop = asyncio.get_running_loop()

    while not shutdown.is_set():
        msg = await loop.run_in_executor(None, consumer.poll, 1.0)  # type: ignore[attr-defined]
        if msg is None:
            continue

        if msg.error():
            if msg.error().code() == kafka_error_cls._PARTITION_EOF:  # noqa: SLF001
                continue
            logger.error("plugin_consumer.kafka_error", error=msg.error())
            continue

        await _process_message(msg, routing_table)


async def _process_message(
    msg: object,
    routing_table: dict[str, list[PluginEventHandler]],
) -> None:
    """Parse a single Kafka message and dispatch to matching handlers."""
    try:
        payload = json.loads(msg.value().decode("utf-8"))  # type: ignore[attr-defined]
        event_type = payload.get("event_type", "")
        sub_type = payload.get("sub_type", "")
        data = payload.get("data", {})

        # Match by sub_type first (e.g. CompoundMentionsUpdated),
        # fall back to event_type (e.g. ArtifactDeleted, PageDeleted)
        matched_key = sub_type if sub_type and sub_type in routing_table else None
        if matched_key is None and event_type and event_type in routing_table:
            matched_key = event_type

        if matched_key:
            await _dispatch(routing_table[matched_key], event_type, matched_key, data)

    except Exception:
        logger.exception("plugin_consumer.message_processing_error")


async def _dispatch(
    handlers: list[PluginEventHandler],
    event_type: str,
    sub_type: str,
    data: dict[str, Any],
) -> None:
    """Dispatch an event to all matching plugin handlers."""
    for handler in handlers:
        try:
            await handler.handle(event_type, sub_type, data)
            logger.info(
                "plugin_consumer.dispatched",
                plugin=handler.plugin_name,
                sub_type=sub_type,
            )
        except Exception:
            logger.exception(
                "plugin_consumer.handler_error",
                plugin=handler.plugin_name,
                sub_type=sub_type,
            )


async def _run_async() -> None:
    """Async entry point — connects to Temporal & MongoDB, then runs concurrently.

    Starts the Kafka consumer loop and plugin Temporal workers side-by-side
    so that event routing and workflow execution both run in this process.
    """
    from motor.motor_asyncio import AsyncIOMotorClient  # noqa: PLC0415
    from temporalio.client import Client as TemporalClient  # noqa: PLC0415
    from temporalio.worker import UnsandboxedWorkflowRunner  # noqa: PLC0415
    from temporalio.worker import Worker as TemporalWorker  # noqa: PLC0415

    from infrastructure.config import settings  # noqa: PLC0415
    from infrastructure.plugins.context import DefaultPluginContext  # noqa: PLC0415
    from infrastructure.plugins.loader import discover_plugins  # noqa: PLC0415

    enabled = settings.enabled_plugins_list
    registry = discover_plugins(enabled, settings.plugin_dir)

    if len(registry) == 0:
        logger.info("plugin_consumer.no_plugins_to_run")
        return

    # Connect to Temporal and MongoDB
    temporal_client = await TemporalClient.connect(settings.temporal_address)
    mongo_client = AsyncIOMotorClient(settings.mongo_uri)
    mongo_db = mongo_client[settings.mongo_db]

    context = DefaultPluginContext(
        page_read_model=None,
        artifact_read_model=None,
        smiles_validator=None,
        embedding_generator=None,
        mongo_db=mongo_db,
        temporal_client=temporal_client,
        plugin_config={},
    )

    # Collect plugin Temporal workflows and activities
    all_workflows = registry.collect_workflows()
    all_activities = registry.collect_activities(context)

    # Build one Temporal worker per unique plugin task queue
    unique_task_queues = {m.effective_task_queue() for m in registry.list_manifests()}

    # Plugin workflows are simple activity dispatchers — disable the Temporal
    # workflow sandbox to avoid import restrictions on third-party libraries
    # (structlog, rich, etc.) that plugins may pull in.
    plugin_workflow_runner = UnsandboxedWorkflowRunner()

    async def run_temporal_workers() -> None:
        workers = []
        for task_queue in sorted(unique_task_queues):
            worker = TemporalWorker(
                temporal_client,
                task_queue=task_queue,
                workflows=all_workflows,
                activities=all_activities,
                max_concurrent_activities=settings.plugin_max_concurrent_activities,
                workflow_runner=plugin_workflow_runner,
            )
            workers.append(worker)
            logger.info("plugin_consumer.temporal_worker_registered", task_queue=task_queue)

        await asyncio.gather(*[w.run() for w in workers])

    logger.info(
        "plugin_consumer.starting_all",
        plugins=registry.list_names(),
        task_queues=sorted(unique_task_queues),
    )

    # Run Kafka consumer + Temporal workers concurrently
    await asyncio.gather(
        run_plugin_consumer(
            registry=registry,
            context=context,
            kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
            kafka_topic=settings.kafka_topic,
        ),
        run_temporal_workers(),
    )


def run_sync() -> None:
    """Entry point for running the plugin consumer as a standalone process."""
    from infrastructure.logging import setup_logging  # noqa: PLC0415

    setup_logging()
    asyncio.run(_run_async())


if __name__ == "__main__":
    run_sync()
