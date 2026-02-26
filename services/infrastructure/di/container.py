from __future__ import annotations

from typing import TYPE_CHECKING

from eventsourcing.application import Application
from lagom import Container
from motor.motor_asyncio import AsyncIOMotorClient

from application.dtos.pdf_dtos import PDFContent
from application.ports.blob_store import BlobStore
from application.ports.cser_service import CserService
from application.ports.embedding_generator import EmbeddingGenerator
from application.ports.external_event_publisher import ExternalEventPublisher
from application.ports.pdf_service import PDFService
from application.ports.repositories.artifact_read_models import ArtifactReadModel
from application.ports.repositories.artifact_repository import ArtifactRepository
from application.ports.repositories.page_read_models import PageReadModel
from application.ports.repositories.page_repository import PageRepository
from application.ports.smiles_validator import SmilesValidator
from application.ports.text_chunker import TextChunker
from application.ports.vector_store import VectorStore
from application.ports.workflow_orchestrator import WorkflowOrchestrator
from application.sagas.artifact_upload_saga import ArtifactUploadSaga
from application.use_cases.artifact_use_cases import (
    AddPagesUseCase,
    CreateArtifactUseCase,
    DeleteArtifactUseCase,
    RemovePagesUseCase,
    UpdateTagsUseCase,
    UpdateTitleMentionUseCase,
)
from application.use_cases.artifact_use_cases import (
    UpdateSummaryCandidateUseCase as UpdateArtifactSummaryCandidateUseCase,
)
from application.use_cases.blob_use_cases import UploadBlobUseCase
from application.use_cases.compound_use_cases import ExtractCompoundMentionsUseCase
from application.use_cases.embedding_use_cases import (
    GeneratePageEmbeddingUseCase,
    SearchSimilarPagesUseCase,
)
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
from application.workflow_use_cases.log_artifcat_sample_use_case import LogArtifactSampleUseCase
from application.workflow_use_cases.trigger_compound_extraction_use_case import (
    TriggerCompoundExtractionUseCase,
)
from application.workflow_use_cases.trigger_embedding_use_case import TriggerEmbeddingUseCase
from domain.value_objects.blob_ref import BlobRef
from domain.value_objects.compound_mention import CompoundMention
from domain.value_objects.embedding_metadata import EmbeddingMetadata
from domain.value_objects.extraction_metadata import ExtractionMetadata
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.text_mention import TextMention
from domain.value_objects.title_mention import TitleMention
from domain.value_objects.workflow_status import WorkflowStatus
from infrastructure.blob_stores.fsspec_blob_store import FsspecBlobStore
from infrastructure.chemistry.rdkit_smiles_validator import RdkitSmilesValidator
from infrastructure.config import settings
from infrastructure.cser.cser_pipeline_service import CserPipelineService
from infrastructure.embeddings.sentence_transformer_generator import SentenceTransformerGenerator
from infrastructure.event_projectors.event_projector import EventProjector
from infrastructure.event_sourced_repositories.artifact_repository import (
    EventSourcedArtifactRepository,
)
from infrastructure.event_sourced_repositories.page_repository import EventSourcedPageRepository
from infrastructure.file_services.py_mu_pfd_service import PyMuPDFService
from infrastructure.kafka.kafka_external_event_streamer import KafkaExternalEventPublisher
from infrastructure.kafka.kafka_publisher import KafkaPublisher
from infrastructure.read_repositories.mongo_read_model_materializer import (
    MongoReadModelMaterializer,
)
from infrastructure.read_repositories.mongo_read_repository import MongoReadRepository
from infrastructure.serialization.pydantic_transcoder import PydanticTranscoding
from infrastructure.temporal.orchestrator import TemporalWorkflowOrchestrator
from infrastructure.text_chunkers.langchain_chunker import LangChainTextChunker
from infrastructure.vector_stores.qdrant_store import QdrantStore

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
        transcoder.register(PydanticTranscoding(WorkflowStatus))
        transcoder.register(PydanticTranscoding(PDFContent))
        transcoder.register(PydanticTranscoding(EmbeddingMetadata))


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

    # Register Pipeline Orchestrator (Temporal)
    container[WorkflowOrchestrator] = lambda _: TemporalWorkflowOrchestrator()

    # Register PDF Service with BlobStore injected
    container[PDFService] = lambda c: PyMuPDFService(blob_store=c[BlobStore])

    # Register CSER Service
    container[CserService] = lambda c: CserPipelineService(blob_store=c[BlobStore])

    # Register SMILES Validator
    container[SmilesValidator] = lambda _: RdkitSmilesValidator()

    # Embedding Generator
    container[EmbeddingGenerator] = lambda _: SentenceTransformerGenerator(
        model_name=settings.embedding_model_name,
        device=settings.embedding_device,
    )

    # Vector Store
    vector_store_instance = QdrantStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection_name=settings.qdrant_collection_name,
        vector_size=384,  # all-MiniLM-L6-v2 default
    )
    container[VectorStore] = vector_store_instance

    # Text Chunker
    container[TextChunker] = lambda _: LangChainTextChunker(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

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

    # Embedding Use Cases
    container[GeneratePageEmbeddingUseCase] = lambda c: GeneratePageEmbeddingUseCase(
        page_repository=c[PageRepository],
        embedding_generator=c[EmbeddingGenerator],
        vector_store=c[VectorStore],
        text_chunker=c[TextChunker],
    )

    container[SearchSimilarPagesUseCase] = lambda c: SearchSimilarPagesUseCase(
        embedding_generator=c[EmbeddingGenerator],
        vector_store=c[VectorStore],
        page_read_model=c[PageReadModel],
        artifact_read_model=c[ArtifactReadModel],
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
        blob_store=c[BlobStore],
    )

    # Register Sagas
    container[ArtifactUploadSaga] = lambda c: ArtifactUploadSaga(
        upload_blob_use_case=c[UploadBlobUseCase],
        create_artifact_use_case=c[CreateArtifactUseCase],
        create_page_use_case=c[CreatePageUseCase],
        add_pages_use_case=c[AddPagesUseCase],
        update_text_mention_use_case=c[UpdateTextMentionUseCase],
        pdf_service=c[PDFService],
    )

    # Compound Extraction Use Case
    container[ExtractCompoundMentionsUseCase] = lambda c: ExtractCompoundMentionsUseCase(
        page_repository=c[PageRepository],
        artifact_repository=c[ArtifactRepository],
        cser_service=c[CserService],
        smiles_validator=c[SmilesValidator],
        external_event_publisher=c[ExternalEventPublisher],
    )

    # Register Workflow Use Cases
    container[LogArtifactSampleUseCase] = lambda c: LogArtifactSampleUseCase(
        artifact_repository=c[ArtifactRepository],
        workflow_orchestrator=c[WorkflowOrchestrator],
    )
    container[TriggerCompoundExtractionUseCase] = lambda c: TriggerCompoundExtractionUseCase(
        page_repository=c[PageRepository],
        workflow_orchestrator=c[WorkflowOrchestrator],
    )
    container[TriggerEmbeddingUseCase] = lambda c: TriggerEmbeddingUseCase(
        page_repository=c[PageRepository],
        workflow_orchestrator=c[WorkflowOrchestrator],
    )

    return container
