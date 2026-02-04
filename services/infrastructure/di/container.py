from __future__ import annotations

from typing import TYPE_CHECKING

from eventsourcing.application import Application
from lagom import Container
from motor.motor_asyncio import AsyncIOMotorClient

from application.ports.blob_store import BlobStore
from application.ports.external_event_publisher import ExternalEventPublisher
from application.ports.repositories.artifact_read_models import ArtifactReadModel
from application.ports.repositories.artifact_repository import ArtifactRepository
from application.ports.repositories.page_read_models import PageReadModel
from application.ports.repositories.page_repository import PageRepository
from application.ports.workflow_orchestrator import WorkflowOrchestrator
from application.use_cases.artifact_use_cases import (
    AddPagesUseCase,
    CreateArtifactUseCase,
    CreateArtifactWithTitleUseCase,
    DeleteArtifactUseCase,
    RemovePagesUseCase,
    UpdateTagsUseCase,
    UpdateTitleMentionUseCase,
)
from application.use_cases.artifact_use_cases import (
    UpdateSummaryCandidateUseCase as UpdateArtifactSummaryCandidateUseCase,
)
from application.use_cases.blob_use_cases import ExtractPdfContentUseCase, UploadBlobUseCase
from application.use_cases.page_use_cases import (
    AddCompoundMentionsUseCase,
    CreatePageUseCase,
    DeletePageUseCase,
    UpdateTagMentionsUseCase,
    UpdateTextMentionUseCase,
)
from application.use_cases.page_use_cases import (
    UpdateSummaryCandidateUseCase as UpdatePageSummaryCandidateUseCase,
)
from domain.value_objects.blob_ref import BlobRef
from domain.value_objects.compound_mention import CompoundMention
from domain.value_objects.extraction_metadata import ExtractionMetadata
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.text_mention import TextMention
from domain.value_objects.title_mention import TitleMention
from infrastructure.blob_stores.fsspec_blob_store import FsspecBlobStore
from infrastructure.config import settings
from infrastructure.event_projectors.event_projector import EventProjector
from infrastructure.event_sourced_repositories.artifact_repository import (
    EventSourcedArtifactRepository,
)
from infrastructure.event_sourced_repositories.page_repository import EventSourcedPageRepository
from infrastructure.kafka.kafka_external_event_streamer import KafkaExternalEventPublisher
from infrastructure.kafka.kafka_publisher import KafkaPublisher
from infrastructure.read_repositories.mongo_read_model_materializer import (
    MongoReadModelMaterializer,
)
from infrastructure.read_repositories.mongo_read_repository import MongoReadRepository
from infrastructure.serialization.pydantic_transcoder import PydanticTranscoding
from infrastructure.temporal.workflow_trigger import TemporalWorkflowOrchestrator

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
        transcoder.register(PydanticTranscoding(TitleMention))
        transcoder.register(PydanticTranscoding(SummaryCandidate))
        transcoder.register(PydanticTranscoding(TagMention))
        transcoder.register(PydanticTranscoding(TextMention))
        transcoder.register(PydanticTranscoding(ExtractionMetadata))
        transcoder.register(PydanticTranscoding(BlobRef))


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
    container[ArtifactRepository] = lambda c: EventSourcedArtifactRepository(
        application=c[Application],
    )

    # Blob storage (fsspec)
    blob_store_instance = FsspecBlobStore(
        base_url=settings.blob_base_url,
        storage_options=getattr(settings, "blob_storage_options", None),
    )
    container[BlobStore] = blob_store_instance

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
        artifact_repository=c[ArtifactRepository],
        external_event_publisher=c[ExternalEventPublisher],
    )
    container[AddCompoundMentionsUseCase] = lambda c: AddCompoundMentionsUseCase(
        page_repository=c[PageRepository],
        external_event_publisher=c[ExternalEventPublisher],
    )
    container[UpdateTagMentionsUseCase] = lambda c: UpdateTagMentionsUseCase(
        page_repository=c[PageRepository],
        external_event_publisher=c[ExternalEventPublisher],
    )
    container[UpdateTextMentionUseCase] = lambda c: UpdateTextMentionUseCase(
        page_repository=c[PageRepository],
        external_event_publisher=c[ExternalEventPublisher],
    )
    container[UpdatePageSummaryCandidateUseCase] = lambda c: UpdatePageSummaryCandidateUseCase(
        page_repository=c[PageRepository],
        external_event_publisher=c[ExternalEventPublisher],
    )
    container[DeletePageUseCase] = lambda c: DeletePageUseCase(
        page_repository=c[PageRepository],
        artifact_repository=c[ArtifactRepository],
        external_event_publisher=c[ExternalEventPublisher],
    )

    # Artifact Use Cases
    container[CreateArtifactUseCase] = lambda c: CreateArtifactUseCase(
        artifact_repository=c[ArtifactRepository],
        external_event_publisher=c[ExternalEventPublisher],
    )
    container[AddPagesUseCase] = lambda c: AddPagesUseCase(
        artifact_repository=c[ArtifactRepository],
        page_repository=c[PageRepository],
        external_event_publisher=c[ExternalEventPublisher],
    )
    container[RemovePagesUseCase] = lambda c: RemovePagesUseCase(
        artifact_repository=c[ArtifactRepository],
        external_event_publisher=c[ExternalEventPublisher],
    )
    container[UpdateTitleMentionUseCase] = lambda c: UpdateTitleMentionUseCase(
        artifact_repository=c[ArtifactRepository],
        external_event_publisher=c[ExternalEventPublisher],
    )
    container[UpdateArtifactSummaryCandidateUseCase] = (
        lambda c: UpdateArtifactSummaryCandidateUseCase(
            artifact_repository=c[ArtifactRepository],
            external_event_publisher=c[ExternalEventPublisher],
        )
    )
    container[UpdateTagsUseCase] = lambda c: UpdateTagsUseCase(
        artifact_repository=c[ArtifactRepository],
        external_event_publisher=c[ExternalEventPublisher],
    )
    container[DeleteArtifactUseCase] = lambda c: DeleteArtifactUseCase(
        artifact_repository=c[ArtifactRepository],
        page_repository=c[PageRepository],
        external_event_publisher=c[ExternalEventPublisher],
    )

    container[UploadBlobUseCase] = lambda c: UploadBlobUseCase(
        artifact_repository=c[ArtifactRepository],
        page_repository=c[PageRepository],
        external_event_publisher=c[ExternalEventPublisher],
        blob_store=c[BlobStore],
        workflow_orchestrator=c[WorkflowOrchestrator],
    )

    # Blob/PDF processing use cases (for Temporal workflows)
    container[ExtractPdfContentUseCase] = lambda c: ExtractPdfContentUseCase(
        blob_store=c[BlobStore],
    )
    container[CreateArtifactWithTitleUseCase] = lambda c: CreateArtifactWithTitleUseCase(
        artifact_repository=c[ArtifactRepository],
        external_event_publisher=c[ExternalEventPublisher],
    )

    # Register Read Model Infrastructure
    container[MongoReadModelMaterializer] = lambda _: MongoReadModelMaterializer()
    container[EventProjector] = lambda c: EventProjector(
        materializer=c[MongoReadModelMaterializer],
    )

    # Register MongoDB Client and Read Repository
    def mongo_client_factory(_: object) -> AsyncIOMotorClient:
        return AsyncIOMotorClient(settings.mongo_uri)

    container[AsyncIOMotorClient] = mongo_client_factory

    def mongo_repository_factory(c: object) -> MongoReadRepository:
        return MongoReadRepository(
            client=c[AsyncIOMotorClient],
            settings=settings,
        )

    container[PageReadModel] = mongo_repository_factory
    container[ArtifactReadModel] = mongo_repository_factory

    # Register Workflow Orchestrator (Port -> Adapter pattern)
    def workflow_orchestrator_factory(_: object) -> WorkflowOrchestrator | None:
        if settings.enable_temporal_workflows:
            return TemporalWorkflowOrchestrator(
                temporal_host=settings.temporal_host,
                task_queue=settings.temporal_task_queue,
            )
        return None

    container[WorkflowOrchestrator] = workflow_orchestrator_factory  # type: ignore[assignment]

    return container
