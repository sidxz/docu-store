"""Plugin consumer — Kafka consumer that routes events to plugin handlers.

This is the single new process that runs all enabled plugins.
It creates per-plugin Kafka consumer groups and starts a shared
Temporal worker for plugin workflows/activities.
"""

from __future__ import annotations

import asyncio
import json
import signal
from typing import Any

import structlog

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

    try:
        from confluent_kafka import Consumer, KafkaError  # noqa: PLC0415
    except ImportError:
        logger.error("plugin_consumer.confluent_kafka_not_installed")
        return

    # One shared consumer for simplicity — filter messages by sub_type
    # Each plugin has its own consumer group but we use a single consumer here
    # with the combined plugin consumer group for MVP simplicity.
    consumer_config = {
        "bootstrap.servers": kafka_bootstrap_servers,
        "group.id": "plugin_consumer",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": True,
    }

    consumer = Consumer(consumer_config)
    consumer.subscribe([kafka_topic])

    shutdown = asyncio.Event()

    def _signal_handler(signum: int, _frame: object) -> None:
        logger.info("plugin_consumer.signal_received", signum=signum)
        shutdown.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        while not shutdown.is_set():
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.error("plugin_consumer.kafka_error", error=msg.error())
                continue

            try:
                payload = json.loads(msg.value().decode("utf-8"))
                event_type = payload.get("event_type", "")
                sub_type = payload.get("sub_type", "")
                data = payload.get("data", {})

                if sub_type and sub_type in routing_table:
                    await _dispatch(routing_table[sub_type], event_type, sub_type, data)

            except Exception:
                logger.exception("plugin_consumer.message_processing_error")

    finally:
        consumer.close()
        logger.info("plugin_consumer.stopped")


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
    from temporalio.worker import Worker as TemporalWorker  # noqa: PLC0415
    from temporalio.worker.workflow_sandbox import (  # noqa: PLC0415
        SandboxedWorkflowRunner,
        SandboxRestrictions,
    )

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

    # Plugin packages may import libraries (structlog, rich, etc.) that are
    # incompatible with the Temporal workflow sandbox.  Pass the entire
    # "plugins" tree through so the sandbox doesn't choke on those imports.
    plugin_sandbox_runner = SandboxedWorkflowRunner(
        restrictions=SandboxRestrictions.default.with_passthrough_modules("plugins"),
    )

    async def run_temporal_workers() -> None:
        workers = []
        for task_queue in sorted(unique_task_queues):
            worker = TemporalWorker(
                temporal_client,
                task_queue=task_queue,
                workflows=all_workflows,
                activities=all_activities,
                max_concurrent_activities=settings.plugin_max_concurrent_activities,
                workflow_runner=plugin_sandbox_runner,
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
