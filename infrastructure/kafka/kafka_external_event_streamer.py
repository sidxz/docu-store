from uuid import UUID

import structlog

from application.dtos.artifact_dtos import ArtifactResponse
from application.dtos.page_dtos import PageResponse
from application.ports.external_event_publisher import ExternalEventPublisher
from infrastructure.kafka.kafka_publisher import KafkaPublisher

logger = structlog.get_logger()


class KafkaExternalEventPublisher(ExternalEventPublisher):
    """Notification service that publishes events to Kafka."""

    def __init__(self, publisher: KafkaPublisher) -> None:
        self.publisher = publisher

    async def notify_page_created(self, page: PageResponse) -> None:
        event = {
            "event_type": "PageCreated",
            "data": page.model_dump(mode="json"),
        }
        await self.publisher.publish(subject="PageCreated", event=event)
        logger.info("kafka notified_page_created", page_id=str(page.page_id))

    async def notify_page_updated(self, page: PageResponse) -> None:
        event = {
            "event_type": "PageUpdated",
            "data": page.model_dump(mode="json"),
        }
        await self.publisher.publish(subject="PageUpdated", event=event)
        logger.info("kafka notified_page_updated", page_id=str(page.page_id))

    async def notify_page_deleted(self, page_id: UUID) -> None:
        event = {
            "event_type": "PageDeleted",
            "data": {"page_id": str(page_id)},
        }
        await self.publisher.publish(subject="PageDeleted", event=event)
        logger.info("kafka notified_page_deleted", page_id=str(page_id))

    async def notify_artifact_created(self, artifact: ArtifactResponse) -> None:
        event = {
            "event_type": "ArtifactCreated",
            "data": artifact.model_dump(mode="json"),
        }
        await self.publisher.publish(subject="ArtifactCreated", event=event)
        logger.info("kafka notified_artifact_created", artifact_id=str(artifact.artifact_id))

    async def notify_artifact_updated(self, artifact: ArtifactResponse) -> None:
        event = {
            "event_type": "ArtifactUpdated",
            "data": artifact.model_dump(mode="json"),
        }
        await self.publisher.publish(subject="ArtifactUpdated", event=event)
        logger.info("kafka notified_artifact_updated", artifact_id=str(artifact.artifact_id))

    async def notify_artifact_deleted(self, artifact_id: UUID) -> None:
        event = {
            "event_type": "ArtifactDeleted",
            "data": {"artifact_id": str(artifact_id)},
        }
        await self.publisher.publish(subject="ArtifactDeleted", event=event)
        logger.info("kafka notified_artifact_deleted", artifact_id=str(artifact_id))
