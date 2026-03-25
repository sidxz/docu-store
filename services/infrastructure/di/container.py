from __future__ import annotations

from typing import TYPE_CHECKING

from eventsourcing.application import Application
from lagom import Container
from motor.motor_asyncio import AsyncIOMotorClient

from application.dtos.pdf_dtos import PDFContent
from application.ports.blob_store import BlobStore
from application.ports.compound_vector_store import CompoundVectorStore
from application.ports.cser_service import CserService
from application.ports.embedding_generator import EmbeddingGenerator
from application.ports.external_event_publisher import ExternalEventPublisher
from application.ports.llm_client import LLMClientPort
from application.ports.ner_extractor import NERExtractorPort
from application.ports.pdf_service import PDFService
from application.ports.permission_registrar import PermissionRegistrar
from application.ports.prompt_repository import PromptRepositoryPort
from application.ports.repositories.artifact_read_models import ArtifactReadModel
from application.ports.repositories.artifact_repository import ArtifactRepository
from application.ports.repositories.dashboard_read_models import DashboardReadModel
from application.ports.repositories.page_read_models import PageReadModel
from application.ports.repositories.page_repository import PageRepository
from application.ports.reranker import Reranker
from application.ports.smiles_validator import SmilesValidator
from application.ports.sparse_embedding_generator import SparseEmbeddingGenerator
from application.ports.structured_extractor import StructuredExtractorPort
from application.ports.summary_vector_store import SummaryVectorStore
from application.ports.text_chunker import TextChunker
from application.ports.title_extractor import TitleExtractorPort
from application.ports.vector_store import VectorStore
from application.ports.workflow_orchestrator import WorkflowOrchestrator
from application.sagas.artifact_upload_saga import ArtifactUploadSaga
from application.use_cases.aggregate_artifact_tags_use_case import AggregateArtifactTagsUseCase
from application.use_cases.artifact_use_cases import (
    AddPagesUseCase,
    CreateArtifactUseCase,
    DeleteArtifactUseCase,
    RemovePagesUseCase,
    UpdateTitleMentionUseCase,
)
from application.use_cases.artifact_use_cases import (
    UpdateSummaryCandidateUseCase as UpdateArtifactSummaryCandidateUseCase,
)
from application.use_cases.artifact_use_cases import (
    UpdateTagMentionsUseCase as UpdateArtifactTagMentionsUseCase,
)
from application.use_cases.blob_use_cases import UploadBlobUseCase
from application.use_cases.compound_use_cases import ExtractCompoundMentionsUseCase
from application.use_cases.embedding_use_cases import (
    GeneratePageEmbeddingUseCase,
    SearchSimilarPagesUseCase,
)
from application.use_cases.extract_document_metadata_use_case import ExtractDocumentMetadataUseCase
from application.use_cases.extract_page_entities_use_case import ExtractPageEntitiesUseCase
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
from application.use_cases.chat_use_cases import (
    CreateConversationUseCase,
    DeleteConversationUseCase,
    GetConversationUseCase,
    ListConversationsUseCase,
    RecordFeedbackUseCase,
    SendMessageUseCase,
)
from application.use_cases.search_use_cases import HierarchicalSearchUseCase, SearchSummariesUseCase
from application.use_cases.smiles_embedding_use_cases import EmbedCompoundSmilesUseCase
from application.use_cases.smiles_search_use_cases import SearchSimilarCompoundsUseCase
from application.use_cases.summarization_use_cases import (
    SummarizeArtifactUseCase,
    SummarizePageUseCase,
)
from application.use_cases.summary_embedding_use_cases import (
    EmbedArtifactSummaryUseCase,
    EmbedPageSummaryUseCase,
)
from application.use_cases.vector_metadata_use_cases import (
    SyncArtifactMetadataToVectorStoreUseCase,
    SyncPageTagsToVectorStoreUseCase,
)
from application.workflow_use_cases.log_artifcat_sample_use_case import LogArtifactSampleUseCase
from application.workflow_use_cases.trigger_artifact_summarization_use_case import (
    TriggerArtifactSummarizationUseCase,
)
from application.workflow_use_cases.trigger_artifact_summary_embedding_use_case import (
    TriggerArtifactSummaryEmbeddingUseCase,
)
from application.workflow_use_cases.trigger_artifact_tag_aggregation_use_case import (
    TriggerArtifactTagAggregationUseCase,
)
from application.workflow_use_cases.trigger_compound_extraction_use_case import (
    TriggerCompoundExtractionUseCase,
)
from application.workflow_use_cases.trigger_doc_metadata_extraction_use_case import (
    TriggerDocMetadataExtractionUseCase,
)
from application.workflow_use_cases.trigger_embedding_use_case import TriggerEmbeddingUseCase
from application.workflow_use_cases.trigger_ner_extraction_use_case import (
    TriggerNERExtractionUseCase,
)
from application.workflow_use_cases.trigger_page_summarization_use_case import (
    TriggerPageSummarizationUseCase,
)
from application.workflow_use_cases.trigger_page_summary_embedding_use_case import (
    TriggerPageSummaryEmbeddingUseCase,
)
from application.workflow_use_cases.trigger_resource_registration_use_case import (
    TriggerResourceRegistrationUseCase,
)
from application.workflow_use_cases.trigger_smiles_embedding_use_case import (
    TriggerSmilesEmbeddingUseCase,
)
from domain.value_objects.author_mention import AuthorMention
from domain.value_objects.blob_ref import BlobRef
from domain.value_objects.compound_mention import CompoundMention
from domain.value_objects.embedding_metadata import EmbeddingMetadata
from domain.value_objects.extraction_metadata import ExtractionMetadata
from domain.value_objects.presentation_date import PresentationDate
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.text_mention import TextMention
from domain.value_objects.title_mention import TitleMention
from infrastructure.auth import sentinel
from infrastructure.blob_stores.fsspec_blob_store import FsspecBlobStore
from infrastructure.chemistry.rdkit_smiles_validator import RdkitSmilesValidator
from infrastructure.config import settings
from infrastructure.cser.cser_pipeline_service import CserPipelineService
from infrastructure.embeddings.chemberta_generator import ChemBertaEmbeddingGenerator
from infrastructure.embeddings.sentence_transformer_generator import SentenceTransformerGenerator
from infrastructure.embeddings.tfidf_sparse_generator import TfidfSparseGenerator
from infrastructure.event_projectors.event_projector import EventProjector
from infrastructure.event_sourced_repositories.artifact_repository import (
    EventSourcedArtifactRepository,
)
from infrastructure.event_sourced_repositories.page_repository import EventSourcedPageRepository
from infrastructure.file_services.font_title_extractor import FontTitleExtractor
from infrastructure.file_services.py_mu_pfd_service import PyMuPDFService
from infrastructure.kafka.kafka_external_event_streamer import KafkaExternalEventPublisher
from infrastructure.kafka.kafka_publisher import KafkaPublisher
from infrastructure.llm.factory import (
    create_chat_llm_client,
    create_llm_client,
    create_prompt_repository,
    create_tool_calling_llm_client,
)
from infrastructure.ner.gliner2_extractor import GLiNER2Extractor
from infrastructure.ner.structflo_ner_extractor import StructfloNERExtractor
from infrastructure.permissions.sentinel_permission_registrar import SentinelPermissionRegistrar
from infrastructure.read_repositories.mongo_read_model_materializer import (
    MongoReadModelMaterializer,
)
from infrastructure.read_repositories.mongo_read_repository import MongoReadRepository
from infrastructure.rerankers.cross_encoder_reranker import CrossEncoderReranker
from infrastructure.serialization.pydantic_transcoder import PydanticTranscoding
from infrastructure.temporal.orchestrator import TemporalWorkflowOrchestrator
from infrastructure.text_chunkers.langchain_chunker import LangChainTextChunker
from infrastructure.vector_stores.compound_qdrant_store import CompoundQdrantStore
from infrastructure.vector_stores.qdrant_store import QdrantStore
from infrastructure.vector_stores.summary_qdrant_store import SummaryQdrantStore

if TYPE_CHECKING:
    from eventsourcing.persistence import JSONTranscoder


class DocuStoreApplication(Application):
    """Subclassing Application is the recommended way to register custom transcodings.

    This allows registering custom transcodings for Pydantic models in the latest
    versions of the eventsourcing library.
    """

    def register_transcodings(self, transcoder: JSONTranscoder) -> None:  # type: ignore[name-defined]
        super().register_transcodings(transcoder)
        transcoder.register(PydanticTranscoding(AuthorMention))
        transcoder.register(PydanticTranscoding(CompoundMention))
        transcoder.register(PydanticTranscoding(PresentationDate))
        transcoder.register(PydanticTranscoding(TitleMention))
        transcoder.register(PydanticTranscoding(SummaryCandidate))
        transcoder.register(PydanticTranscoding(TagMention))
        transcoder.register(PydanticTranscoding(TextMention))
        transcoder.register(PydanticTranscoding(ExtractionMetadata))
        transcoder.register(PydanticTranscoding(BlobRef))
        transcoder.register(PydanticTranscoding(PDFContent))
        transcoder.register(PydanticTranscoding(EmbeddingMetadata))


def create_container() -> Container:  # noqa: PLR0915
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

    from application.ports.repositories.tag_browse_read_model import (
        TagBrowseReadModel,
    )
    from application.ports.repositories.tag_dictionary_read_model import (
        TagDictionaryReadModel,
    )

    container[TagBrowseReadModel] = mongo_repository_factory
    container[TagDictionaryReadModel] = mongo_repository_factory
    container[DashboardReadModel] = mongo_repository_factory

    from application.ports.repositories.user_activity_store import UserActivityStore
    from application.ports.repositories.user_preferences_store import UserPreferencesStore
    from infrastructure.read_repositories.mongo_user_store import MongoUserStore

    def user_store_factory(c: object) -> MongoUserStore:
        return MongoUserStore(
            client=c[AsyncIOMotorClient],
            settings=settings,
        )

    container[UserPreferencesStore] = user_store_factory
    container[UserActivityStore] = user_store_factory

    from application.ports.analytics_read_model import AnalyticsReadModel  # noqa: PLC0415
    from infrastructure.read_repositories.mongo_analytics_store import MongoAnalyticsStore  # noqa: PLC0415

    container[AnalyticsReadModel] = lambda c: MongoAnalyticsStore(
        client=c[AsyncIOMotorClient],
        db_name=settings.mongo_db,
        artifacts_collection_name=settings.mongo_artifacts_collection,
    )

    # Register Pipeline Orchestrator (Temporal)
    container[WorkflowOrchestrator] = lambda _: TemporalWorkflowOrchestrator()

    # Permission Registrar (Sentinel entity-level permissions)
    container[PermissionRegistrar] = lambda _: SentinelPermissionRegistrar(sentinel.permissions)
    container[TriggerResourceRegistrationUseCase] = lambda c: TriggerResourceRegistrationUseCase(
        permission_registrar=c[PermissionRegistrar],
    )

    # Register PDF Service with BlobStore injected
    container[PDFService] = lambda c: PyMuPDFService(blob_store=c[BlobStore])

    # Register CSER Service
    container[CserService] = lambda c: CserPipelineService(blob_store=c[BlobStore])

    # Register Title Extractor (font-based, PyMuPDF)
    container[TitleExtractorPort] = lambda _: FontTitleExtractor()

    # Register Structured Extractor (GLiNER2 — document metadata)
    container[StructuredExtractorPort] = lambda _: GLiNER2Extractor(
        model_name=settings.gliner2_model_name,
    )

    # Register NER Extractor (dual-mode: fast + LLM, reuses configured LLM settings)
    container[NERExtractorPort] = lambda _: StructfloNERExtractor(
        model_id=settings.llm_model_name,
        model_url=settings.llm_base_url,
        max_char_buffer=settings.ner_max_char_buffer,
    )

    # Register SMILES Validator
    container[SmilesValidator] = lambda _: RdkitSmilesValidator()

    # Embedding Generator (singleton — model loaded once, reused across requests)
    embedding_generator_instance = SentenceTransformerGenerator(
        model_name=settings.embedding_model_name,
        device=settings.embedding_device,
        query_prefix=settings.embedding_query_prefix,
        document_prefix=settings.embedding_document_prefix,
    )
    container[EmbeddingGenerator] = embedding_generator_instance

    # Vector Store (text embeddings — page chunks)
    vector_store_instance = QdrantStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection_name=settings.qdrant_collection_name,
        vector_size=settings.embedding_dimensions,
    )
    container[VectorStore] = vector_store_instance

    # Compound Vector Store (SMILES embeddings — ChemBERTa)
    compound_vector_store_instance = CompoundQdrantStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection_name=settings.qdrant_compound_collection_name,
    )
    container[CompoundVectorStore] = compound_vector_store_instance

    # Summary Vector Store (page + artifact summary embeddings)
    summary_vector_store_instance = SummaryQdrantStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection_name=settings.qdrant_summary_collection_name,
        vector_size=settings.embedding_dimensions,
    )
    container[SummaryVectorStore] = summary_vector_store_instance

    # ChemBERTa embedding generator (SMILES) — singleton
    chemberta_instance = ChemBertaEmbeddingGenerator(
        model_name=settings.smiles_embedding_model_name,
        device=settings.smiles_embedding_device,
    )
    container[ChemBertaEmbeddingGenerator] = chemberta_instance

    # Text Chunker — singleton (stateless, no model)
    text_chunker_instance = LangChainTextChunker(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    container[TextChunker] = text_chunker_instance

    # Sparse Embedding Generator (hashing-based for hybrid search)
    sparse_generator_instance = TfidfSparseGenerator()
    container[SparseEmbeddingGenerator] = sparse_generator_instance

    # Cross-encoder reranker (Stage 2 — reranks retrieval candidates) — singleton
    if settings.reranker_enabled:
        reranker_instance = CrossEncoderReranker(
            model_name=settings.reranker_model_name,
            device=settings.reranker_device,
        )
        container[Reranker] = reranker_instance
    else:
        container[Reranker] = None  # type: ignore[assignment]

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
        sparse_embedding_generator=c[SparseEmbeddingGenerator],
        artifact_repository=c[ArtifactRepository],
    )

    container[SearchSimilarPagesUseCase] = lambda c: SearchSimilarPagesUseCase(
        embedding_generator=c[EmbeddingGenerator],
        vector_store=c[VectorStore],
        page_read_model=c[PageReadModel],
        artifact_read_model=c[ArtifactReadModel],
        sparse_embedding_generator=c[SparseEmbeddingGenerator],
        reranker=c[Reranker],
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
    container[UpdateArtifactTagMentionsUseCase] = lambda c: UpdateArtifactTagMentionsUseCase(
        artifact_repository=c[ArtifactRepository],
        external_event_publisher=c[ExternalEventPublisher],
    )
    container[DeleteArtifactUseCase] = lambda c: DeleteArtifactUseCase(
        artifact_repository=c[ArtifactRepository],
        page_repository=c[PageRepository],
        external_event_publisher=c[ExternalEventPublisher],
        vector_store=c[VectorStore],
        compound_vector_store=c[CompoundVectorStore],
        summary_vector_store=c[SummaryVectorStore],
        blob_store=c[BlobStore],
        permission_registrar=c[PermissionRegistrar],
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
        blob_store=c[BlobStore],
        permission_registrar=c[PermissionRegistrar],
    )

    # NER Extraction Use Cases
    container[ExtractPageEntitiesUseCase] = lambda c: ExtractPageEntitiesUseCase(
        page_repository=c[PageRepository],
        artifact_repository=c[ArtifactRepository],
        ner_extractor=c[NERExtractorPort],
        external_event_publisher=c[ExternalEventPublisher],
    )
    container[AggregateArtifactTagsUseCase] = lambda c: AggregateArtifactTagsUseCase(
        artifact_repository=c[ArtifactRepository],
        page_repository=c[PageRepository],
        external_event_publisher=c[ExternalEventPublisher],
    )
    container[TriggerNERExtractionUseCase] = lambda c: TriggerNERExtractionUseCase(
        workflow_orchestrator=c[WorkflowOrchestrator],
    )

    # Document Metadata Extraction Use Cases
    container[ExtractDocumentMetadataUseCase] = lambda c: ExtractDocumentMetadataUseCase(
        page_repository=c[PageRepository],
        artifact_repository=c[ArtifactRepository],
        structured_extractor=c[StructuredExtractorPort],
        llm_client=c[LLMClientPort],
        prompt_repository=c[PromptRepositoryPort],
        title_extractor=c[TitleExtractorPort],
        blob_store=c[BlobStore],
        external_event_publisher=c[ExternalEventPublisher],
    )
    container[TriggerDocMetadataExtractionUseCase] = lambda c: TriggerDocMetadataExtractionUseCase(
        page_repository=c[PageRepository],
        workflow_orchestrator=c[WorkflowOrchestrator],
    )
    container[TriggerArtifactTagAggregationUseCase] = (
        lambda c: TriggerArtifactTagAggregationUseCase(
            workflow_orchestrator=c[WorkflowOrchestrator],
        )
    )

    # Compound Extraction Use Case
    container[ExtractCompoundMentionsUseCase] = lambda c: ExtractCompoundMentionsUseCase(
        page_repository=c[PageRepository],
        artifact_repository=c[ArtifactRepository],
        cser_service=c[CserService],
        smiles_validator=c[SmilesValidator],
        external_event_publisher=c[ExternalEventPublisher],
    )

    # SMILES Embedding Use Case
    container[EmbedCompoundSmilesUseCase] = lambda c: EmbedCompoundSmilesUseCase(
        page_repository=c[PageRepository],
        smiles_embedding_generator=c[ChemBertaEmbeddingGenerator],
        compound_vector_store=c[CompoundVectorStore],
    )

    # SMILES Search Use Case
    container[SearchSimilarCompoundsUseCase] = lambda c: SearchSimilarCompoundsUseCase(
        smiles_embedding_generator=c[ChemBertaEmbeddingGenerator],
        compound_vector_store=c[CompoundVectorStore],
        artifact_read_model=c[ArtifactReadModel],
        smiles_validator=c[SmilesValidator],
    )

    # Register Workflow Use Cases
    container[LogArtifactSampleUseCase] = lambda c: LogArtifactSampleUseCase(
        workflow_orchestrator=c[WorkflowOrchestrator],
    )
    container[TriggerCompoundExtractionUseCase] = lambda c: TriggerCompoundExtractionUseCase(
        workflow_orchestrator=c[WorkflowOrchestrator],
    )
    container[TriggerEmbeddingUseCase] = lambda c: TriggerEmbeddingUseCase(
        workflow_orchestrator=c[WorkflowOrchestrator],
    )
    container[TriggerSmilesEmbeddingUseCase] = lambda c: TriggerSmilesEmbeddingUseCase(
        workflow_orchestrator=c[WorkflowOrchestrator],
    )

    # LLM Infrastructure (shared — provider selected via LLM_PROVIDER config)
    container[LLMClientPort] = lambda _: create_llm_client(settings)
    container[PromptRepositoryPort] = lambda _: create_prompt_repository(settings)

    # Summarization Use Cases
    container[SummarizePageUseCase] = lambda c: SummarizePageUseCase(
        page_repository=c[PageRepository],
        artifact_repository=c[ArtifactRepository],
        llm_client=c[LLMClientPort],
        prompt_repository=c[PromptRepositoryPort],
        blob_store=c[BlobStore],
        external_event_publisher=c[ExternalEventPublisher],
    )
    container[TriggerPageSummarizationUseCase] = lambda c: TriggerPageSummarizationUseCase(
        workflow_orchestrator=c[WorkflowOrchestrator],
    )

    # Artifact Summarization Use Cases
    container[SummarizeArtifactUseCase] = lambda c: SummarizeArtifactUseCase(
        artifact_repository=c[ArtifactRepository],
        page_repository=c[PageRepository],
        llm_client=c[LLMClientPort],
        prompt_repository=c[PromptRepositoryPort],
        external_event_publisher=c[ExternalEventPublisher],
        batch_size=settings.artifact_summarization_batch_size,
    )
    container[TriggerArtifactSummarizationUseCase] = lambda c: TriggerArtifactSummarizationUseCase(
        artifact_repository=c[ArtifactRepository],
        page_read_model=c[PageReadModel],
        workflow_orchestrator=c[WorkflowOrchestrator],
    )

    # Batch re-embed use cases
    from application.use_cases.batch_reembed_use_cases import (  # noqa: PLC0415
        BatchReEmbedArtifactPagesUseCase,
    )
    from application.workflow_use_cases.trigger_batch_reembed_use_case import (  # noqa: PLC0415
        TriggerBatchReEmbedUseCase,
    )

    container[BatchReEmbedArtifactPagesUseCase] = lambda c: BatchReEmbedArtifactPagesUseCase(
        artifact_repository=c[ArtifactRepository],
        page_repository=c[PageRepository],
        embedding_generator=c[EmbeddingGenerator],
        vector_store=c[VectorStore],
        text_chunker=c[TextChunker],
    )
    container[TriggerBatchReEmbedUseCase] = lambda c: TriggerBatchReEmbedUseCase(
        workflow_orchestrator=c[WorkflowOrchestrator],
    )

    # Summary Embedding Use Cases
    container[EmbedPageSummaryUseCase] = lambda c: EmbedPageSummaryUseCase(
        page_repository=c[PageRepository],
        artifact_repository=c[ArtifactRepository],
        embedding_generator=c[EmbeddingGenerator],
        summary_vector_store=c[SummaryVectorStore],
    )
    container[EmbedArtifactSummaryUseCase] = lambda c: EmbedArtifactSummaryUseCase(
        artifact_repository=c[ArtifactRepository],
        embedding_generator=c[EmbeddingGenerator],
        summary_vector_store=c[SummaryVectorStore],
    )
    container[TriggerPageSummaryEmbeddingUseCase] = lambda c: TriggerPageSummaryEmbeddingUseCase(
        workflow_orchestrator=c[WorkflowOrchestrator],
    )
    container[TriggerArtifactSummaryEmbeddingUseCase] = (
        lambda c: TriggerArtifactSummaryEmbeddingUseCase(
            workflow_orchestrator=c[WorkflowOrchestrator],
        )
    )

    # Vector Metadata Sync Use Cases
    container[SyncPageTagsToVectorStoreUseCase] = lambda c: SyncPageTagsToVectorStoreUseCase(
        page_repository=c[PageRepository],
        vector_store=c[VectorStore],
        summary_vector_store=c[SummaryVectorStore],
    )
    container[SyncArtifactMetadataToVectorStoreUseCase] = (
        lambda c: SyncArtifactMetadataToVectorStoreUseCase(
            artifact_repository=c[ArtifactRepository],
            vector_store=c[VectorStore],
            summary_vector_store=c[SummaryVectorStore],
        )
    )

    # Search Use Cases
    container[SearchSummariesUseCase] = lambda c: SearchSummariesUseCase(
        embedding_generator=c[EmbeddingGenerator],
        summary_vector_store=c[SummaryVectorStore],
        artifact_read_model=c[ArtifactReadModel],
    )
    container[HierarchicalSearchUseCase] = lambda c: HierarchicalSearchUseCase(
        embedding_generator=c[EmbeddingGenerator],
        vector_store=c[VectorStore],
        summary_vector_store=c[SummaryVectorStore],
        page_read_model=c[PageReadModel],
        artifact_read_model=c[ArtifactReadModel],
        reranker=c[Reranker],
        sparse_embedding_generator=c[SparseEmbeddingGenerator],
    )

    # --- Chat (Agentic RAG) ---
    from application.ports.chat_agent import ChatAgentPort  # noqa: PLC0415
    from application.services.chat_agent_router import ChatAgentRouter  # noqa: PLC0415
    from application.ports.chat_repository import ChatRepository  # noqa: PLC0415
    from infrastructure.chat.agent import ChatAgent  # noqa: PLC0415
    from infrastructure.chat.mongo_chat_repository import MongoChatRepository  # noqa: PLC0415
    from infrastructure.chat.nodes.answer_formatting import AnswerFormattingNode  # noqa: PLC0415
    from infrastructure.chat.nodes.answer_synthesis import AnswerSynthesisNode  # noqa: PLC0415
    from infrastructure.chat.nodes.grounding_verification import GroundingVerificationNode  # noqa: PLC0415
    from infrastructure.chat.nodes.question_analysis import QuestionAnalysisNode  # noqa: PLC0415
    from infrastructure.chat.nodes.retrieval import RetrievalNode  # noqa: PLC0415
    from infrastructure.chat.thinking_agent import ThinkingAgent  # noqa: PLC0415
    from infrastructure.chat.nodes.query_planning import QueryPlanningNode  # noqa: PLC0415
    from infrastructure.chat.nodes.agentic_retrieval import AgenticRetrievalNode  # noqa: PLC0415
    from infrastructure.chat.nodes.context_assembly import ContextAssemblyNode  # noqa: PLC0415
    from infrastructure.chat.nodes.adaptive_synthesis import AdaptiveSynthesisNode  # noqa: PLC0415
    from infrastructure.chat.nodes.inline_verification import InlineVerificationNode  # noqa: PLC0415
    from infrastructure.chat.tools.retrieval_tools import ToolRegistry  # noqa: PLC0415

    # Chat LLM client (separate from batch LLM, falls back to same settings)
    chat_llm_client = create_chat_llm_client(settings)

    container[ChatRepository] = lambda c: MongoChatRepository(
        client=c[AsyncIOMotorClient],
        db_name=settings.mongo_db,
    )

    # --- Quick Mode nodes (existing pipeline) ---
    container[QuestionAnalysisNode] = lambda c: QuestionAnalysisNode(
        llm_client=chat_llm_client,
        prompt_repository=c[PromptRepositoryPort],
    )
    container[RetrievalNode] = lambda c: RetrievalNode(
        hierarchical_search=c[HierarchicalSearchUseCase],
        summary_search=c[SearchSummariesUseCase],
        page_read_model=c[PageReadModel],
        max_results=settings.chat_max_retrieval_results,
    )
    container[AnswerSynthesisNode] = lambda c: AnswerSynthesisNode(
        llm_client=chat_llm_client,
        prompt_repository=c[PromptRepositoryPort],
    )
    container[GroundingVerificationNode] = lambda c: GroundingVerificationNode(
        llm_client=chat_llm_client,
        prompt_repository=c[PromptRepositoryPort],
    )

    container[AnswerFormattingNode] = lambda c: AnswerFormattingNode(
        llm_client=chat_llm_client,
        prompt_repository=c[PromptRepositoryPort],
    )

    quick_agent = lambda c: ChatAgent(
        question_analysis=c[QuestionAnalysisNode],
        retrieval=c[RetrievalNode],
        answer_synthesis=c[AnswerSynthesisNode],
        grounding_verification=c[GroundingVerificationNode],
        answer_formatting=c[AnswerFormattingNode],
        max_retries=settings.chat_max_retries,
    )

    # --- Thinking Mode nodes (v2 — agentic retrieval) ---
    container[QueryPlanningNode] = lambda c: QueryPlanningNode(
        llm_client=chat_llm_client,
        prompt_repository=c[PromptRepositoryPort],
        ner_extractor=c[NERExtractorPort],
        structured_extractor=c[StructuredExtractorPort],
    )

    # Tool-calling LLM + tool registry for agentic retrieval
    tool_calling_llm = create_tool_calling_llm_client(settings)
    container[ToolRegistry] = lambda c: ToolRegistry(
        hierarchical_search=c[HierarchicalSearchUseCase],
        summary_search=c[SearchSummariesUseCase],
        page_read_model=c[PageReadModel],
        tag_dictionary=c[TagDictionaryReadModel],
    )
    container[AgenticRetrievalNode] = lambda c: AgenticRetrievalNode(
        tool_llm=tool_calling_llm,
        tool_registry=c[ToolRegistry],
        prompt_repository=c[PromptRepositoryPort],
    )

    container[ContextAssemblyNode] = lambda _: ContextAssemblyNode()
    container[AdaptiveSynthesisNode] = lambda c: AdaptiveSynthesisNode(
        llm_client=chat_llm_client,
        prompt_repository=c[PromptRepositoryPort],
    )
    container[InlineVerificationNode] = lambda c: InlineVerificationNode(
        llm_client=chat_llm_client,
        prompt_repository=c[PromptRepositoryPort],
    )

    thinking_agent = lambda c: ThinkingAgent(
        query_planning=c[QueryPlanningNode],
        agentic_retrieval=c[AgenticRetrievalNode],
        context_assembly=c[ContextAssemblyNode],
        adaptive_synthesis=c[AdaptiveSynthesisNode],
        inline_verification=c[InlineVerificationNode],
        answer_formatting=c[AnswerFormattingNode],
        tag_dictionary=c[TagDictionaryReadModel],
        max_retries=settings.chat_max_retries,
    )

    # --- Deep Thinking Mode (thinking + page images) ---
    deep_thinking_agent = lambda c: ThinkingAgent(
        query_planning=c[QueryPlanningNode],
        agentic_retrieval=c[AgenticRetrievalNode],
        context_assembly=c[ContextAssemblyNode],
        adaptive_synthesis=c[AdaptiveSynthesisNode],
        inline_verification=c[InlineVerificationNode],
        answer_formatting=c[AnswerFormattingNode],
        tag_dictionary=c[TagDictionaryReadModel],
        max_retries=settings.chat_max_retries,
        blob_store=c[BlobStore],
        include_images=True,
    )

    # --- Agent Router (dispatches to quick, thinking, or deep thinking) ---
    container[ChatAgentPort] = lambda c: ChatAgentRouter(
        quick_agent=quick_agent(c),
        thinking_agent=thinking_agent(c),
        deep_thinking_agent=deep_thinking_agent(c),
        default_mode=settings.chat_default_mode,
    )

    # Chat Use Cases
    container[CreateConversationUseCase] = lambda c: CreateConversationUseCase(
        chat_repository=c[ChatRepository],
    )
    container[ListConversationsUseCase] = lambda c: ListConversationsUseCase(
        chat_repository=c[ChatRepository],
    )
    container[GetConversationUseCase] = lambda c: GetConversationUseCase(
        chat_repository=c[ChatRepository],
    )
    container[DeleteConversationUseCase] = lambda c: DeleteConversationUseCase(
        chat_repository=c[ChatRepository],
    )
    container[SendMessageUseCase] = lambda c: SendMessageUseCase(
        chat_repository=c[ChatRepository],
        chat_agent=c[ChatAgentPort],
    )
    container[RecordFeedbackUseCase] = lambda c: RecordFeedbackUseCase(
        chat_repository=c[ChatRepository],
    )

    return container
