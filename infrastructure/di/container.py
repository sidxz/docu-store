from __future__ import annotations

from typing import TYPE_CHECKING

from eventsourcing.application import Application
from lagom import Container
from motor.motor_asyncio import AsyncIOMotorClient

from application.ports.external_event_publisher import ExternalEventPublisher
from application.ports.repositories.page_read_models import PageReadModel
from application.ports.repositories.page_repository import PageRepository
from application.use_cases.page_use_cases import AddCompoundMentionsUseCase, CreatePageUseCase
from domain.value_objects.compound_mention import CompoundMention
from infrastructure.config import settings
from infrastructure.event_projectors.event_projector import EventProjector
from infrastructure.event_sourced_repositories.page_repository import EventSourcedPageRepository
from infrastructure.kafka.kafka_external_event_streamer import KafkaExternalEventPublisher
from infrastructure.kafka.kafka_publisher import KafkaPublisher
from infrastructure.read_repositories.mongo_read_model_materializer import (
    MongoReadModelMaterializer,
)
from infrastructure.read_repositories.mongo_read_repository import MongoReadRepository
from infrastructure.serialization.pydantic_transcoder import PydanticTranscoding

if TYPE_CHECKING:
    from eventsourcing.persistence import JSONTranscoder


class DocuStoreApplication(Application):
    """Subclassing Application is the recommended way to register custom transcodings.

    This allows registering custom transcodings for Pydantic models in the latest
    versions of the eventsourcing library.
    """

    def register_transcodings(self, transcoder: JSONTranscoder) -> None:  # type: ignore[name-defined]
        super().register_transcodings(transcoder)
        transcoder.register(PydanticTranscoding(CompoundMention))


def create_container() -> Container:
    container = Container()

    # Initialize our custom Application subclass
    docu_store_application = DocuStoreApplication(
        env={
            "PERSISTENCE_MODULE": "eventsourcing_kurrentdb",
            "KURRENTDB_URI": settings.eventstoredb_uri,
        },
    )

    # Register Application instance
    container[Application] = docu_store_application

    # Register Repositories
    container[PageRepository] = lambda c: EventSourcedPageRepository(
        application=c[Application],
    )

    # Register Kafka Publisher
    kafka_publisher_instance = (
        KafkaPublisher() if settings.enable_external_event_streaming else None
    )
    if kafka_publisher_instance:
        # Initialize the Kafka publisher connection in a sync context
        # The connect() method will be called asynchronously when first used
        container[KafkaPublisher] = kafka_publisher_instance

    # Register Kafka External Event Publisher
    # Infrastructure - Notifications
    if settings.enable_external_event_streaming:
        container[ExternalEventPublisher] = lambda c: KafkaExternalEventPublisher(
            publisher=c[KafkaPublisher],
        )
    else:
        container[ExternalEventPublisher] = lambda _: None  # type: ignore[return-value]

    # Register Use Cases
    # Page Use Cases
    container[CreatePageUseCase] = lambda c: CreatePageUseCase(
        page_repository=c[PageRepository],
        external_event_publisher=c[ExternalEventPublisher],
    )
    container[AddCompoundMentionsUseCase] = lambda c: AddCompoundMentionsUseCase(
        page_repository=c[PageRepository],
    )

    # Register Read Model Infrastructure
    container[MongoReadModelMaterializer] = lambda _: MongoReadModelMaterializer()
    container[EventProjector] = lambda c: EventProjector(
        materializer=c[MongoReadModelMaterializer],
    )

    # Register MongoDB Client and Read Repository
    container[AsyncIOMotorClient] = lambda _: AsyncIOMotorClient(settings.mongo_uri)
    container[PageReadModel] = lambda c: MongoReadRepository(
        client=c[AsyncIOMotorClient],
        settings=settings,
    )

    return container
