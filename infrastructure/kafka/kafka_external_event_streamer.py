import structlog

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
