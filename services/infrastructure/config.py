from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # make it absolute so reload/CWD doesn't break it
        env_file=Path(__file__).resolve().parents[1] / ".env",  # adjust parents[] if needed
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="DocuStore", validation_alias="APP_NAME")
    app_env: Literal["development", "staging", "production"] = Field(
        default="development",
        validation_alias="APP_ENV",
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_dir: Path = Field(
        default=Path(__file__).resolve().parents[1] / "logs",
        validation_alias="LOG_DIR",
    )

    # EventStoreDB
    eventstoredb_uri: str = Field(
        default="esdb://localhost:2113?tls=false",
        validation_alias="EVENTSTOREDB_URI",
    )

    # Kafka
    enable_external_event_streaming: bool = Field(
        default=True,
        validation_alias="ENABLE_EXTERNAL_EVENT_STREAMING",
    )
    kafka_bootstrap_servers: str = Field(
        default="localhost:19092",
        validation_alias="KAFKA_BOOTSTRAP_SERVERS",
    )
    kafka_topic: str = Field(default="docu_store_events", validation_alias="KAFKA_TOPIC")

    # API
    api_host: str = Field(default="127.0.0.1", validation_alias="API_HOST")
    api_port: int = Field(default=8000, validation_alias="API_PORT")

    # MongoDB
    mongo_uri: str = Field(
        default="mongodb://localhost:27017/?replicaSet=rs0",
        validation_alias="MONGO_URI",
    )
    mongo_db: str = Field(default="docu_store", validation_alias="MONGO_DB")
    mongo_pages_collection: str = Field(
        default="page_read_models",
        validation_alias="MONGO_PAGES_COLLECTION",
    )
    mongo_artifacts_collection: str = Field(
        default="artifact_read_models",
        validation_alias="MONGO_ARTIFACTS_COLLECTION",
    )
    mongo_tracking_collection: str = Field(
        default="read_model_tracking",
        validation_alias="MONGO_TRACKING_COLLECTION",
    )
    mongo_tag_dictionary_collection: str = Field(
        default="tag_dictionary",
        validation_alias="MONGO_TAG_DICTIONARY_COLLECTION",
    )
    mongo_user_preferences_collection: str = Field(
        default="user_preferences",
        validation_alias="MONGO_USER_PREFERENCES_COLLECTION",
    )
    mongo_user_activity_collection: str = Field(
        default="user_activity",
        validation_alias="MONGO_USER_ACTIVITY_COLLECTION",
    )

    # Blob Storage
    blob_base_url: str = Field(
        default="file://" + str(Path(__file__).resolve().parents[1] / "blobs"),
        validation_alias="BLOB_BASE_URL",
    )
    blob_storage_options: dict = {}

    # Temporal
    temporal_address: str = Field(
        default="localhost:7233",
        validation_alias="TEMPORAL_ADDRESS",
    )
    temporal_max_concurrent_activities: int = Field(
        default=10,
        validation_alias="TEMPORAL_MAX_CONCURRENT_ACTIVITIES",
        description="Max concurrent Temporal activities. Lower on dev to save memory.",
    )
    temporal_llm_task_queue: str = Field(
        default="llm_processing",
        validation_alias="TEMPORAL_LLM_TASK_QUEUE",
    )
    temporal_max_concurrent_llm_activities: int = Field(
        default=2,
        validation_alias="TEMPORAL_MAX_CONCURRENT_LLM_ACTIVITIES",
        description="Max concurrent LLM activities. Ollama: 1-2, Cloud API: 5-10.",
    )

    # Qdrant (Vector Store)
    qdrant_url: str = Field(
        default="http://localhost:6333",
        validation_alias="QDRANT_URL",
    )
    qdrant_api_key: str | None = Field(
        default=None,
        validation_alias="QDRANT_API_KEY",
    )
    qdrant_collection_name: str = Field(
        default="page_embeddings",
        validation_alias="QDRANT_COLLECTION_NAME",
    )
    qdrant_compound_collection_name: str = Field(
        default="compound_embeddings",
        validation_alias="QDRANT_COMPOUND_COLLECTION_NAME",
    )
    qdrant_summary_collection_name: str = Field(
        default="summary_embeddings",
        validation_alias="QDRANT_SUMMARY_COLLECTION_NAME",
    )

    # Embeddings
    embedding_model_provider: Literal["sentence-transformers", "openai"] = Field(
        default="sentence-transformers",
        validation_alias="EMBEDDING_MODEL_PROVIDER",
    )
    embedding_model_name: str = Field(
        default="nomic-ai/nomic-embed-text-v1.5",
        validation_alias="EMBEDDING_MODEL_NAME",
    )
    embedding_dimensions: int = Field(
        default=768,
        validation_alias="EMBEDDING_DIMENSIONS",
        description="Vector dimensionality (768 for nomic, 384 for MiniLM)",
    )
    embedding_device: Literal["cpu", "cuda", "mps"] = Field(
        default="cpu",
        validation_alias="EMBEDDING_DEVICE",
    )
    embedding_query_prefix: str = Field(
        default="search_query: ",
        validation_alias="EMBEDDING_QUERY_PREFIX",
        description="Prefix for query text (nomic requires 'search_query: ')",
    )
    embedding_document_prefix: str = Field(
        default="search_document: ",
        validation_alias="EMBEDDING_DOCUMENT_PREFIX",
        description="Prefix for document text (nomic requires 'search_document: ')",
    )

    # SMILES / ChemBERTa embeddings
    smiles_embedding_model_name: str = Field(
        default="DeepChem/ChemBERTa-77M-MTR",
        validation_alias="SMILES_EMBEDDING_MODEL_NAME",
    )
    smiles_embedding_device: Literal["cpu", "cuda", "mps"] = Field(
        default="cpu",
        validation_alias="SMILES_EMBEDDING_DEVICE",
    )

    # Cross-encoder reranker
    reranker_model_name: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-12-v2",
        validation_alias="RERANKER_MODEL_NAME",
    )
    reranker_device: Literal["cpu", "cuda", "mps"] = Field(
        default="cpu",
        validation_alias="RERANKER_DEVICE",
    )
    reranker_enabled: bool = Field(
        default=True,
        validation_alias="RERANKER_ENABLED",
    )

    # Text Chunking
    chunk_size: int = Field(
        default=1000,
        validation_alias="CHUNK_SIZE",
        description="Max characters per chunk (~200-250 tokens). Adjust when switching models.",
    )
    chunk_overlap: int = Field(
        default=200,
        validation_alias="CHUNK_OVERLAP",
        description="Overlapping characters between chunks. Typically 10-20% of chunk_size.",
    )

    # NER (structflo / langextract)
    ner_max_char_buffer: int = Field(
        default=5000,
        validation_alias="NER_MAX_CHAR_BUFFER",
        description="Max chars per LLM chunk in NER extraction. Higher = fewer LLM calls but more tokens per call.",
    )

    # GLiNER2 (structured extraction for document metadata)
    gliner2_model_name: str = Field(
        default="fastino/gliner2-large-v1",
        validation_alias="GLINER2_MODEL_NAME",
        description="GLiNER2 model for structured document metadata extraction.",
    )

    # Artifact Summarization
    artifact_summarization_batch_size: int = Field(
        default=10,
        validation_alias="ARTIFACT_SUMMARIZATION_BATCH_SIZE",
        description="Number of page summaries per batch in the sliding-window artifact summarization chain.",
    )

    # For OpenAI (when provider is "openai")
    openai_api_key: str | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )

    # LLM (shared infrastructure — used by summarization and future features)
    llm_provider: Literal["ollama", "openai", "gemini"] = Field(
        default="ollama",
        validation_alias="LLM_PROVIDER",
    )
    llm_model_name: str = Field(
        default="gemma3:27b",
        validation_alias="LLM_MODEL_NAME",
    )
    llm_base_url: str = Field(
        default="http://localhost:11434",
        validation_alias="LLM_BASE_URL",
        description="Ollama base URL. Ignored for cloud providers.",
    )
    llm_api_key: str | None = Field(
        default=None,
        validation_alias="LLM_API_KEY",
        description="API key for cloud LLM providers (OpenAI, Gemini). Not needed for Ollama.",
    )
    llm_temperature: float = Field(
        default=0.1,
        validation_alias="LLM_TEMPERATURE",
        description="Low temperature for deterministic summaries.",
    )

    # Chat LLM (separate from batch LLM — allows different model/temperature for interactive chat)
    chat_llm_provider: Literal["ollama", "openai", "gemini"] | None = Field(
        default=None,
        validation_alias="CHAT_LLM_PROVIDER",
        description="LLM provider for chat. Falls back to llm_provider if not set.",
    )
    chat_llm_model_name: str | None = Field(
        default=None,
        validation_alias="CHAT_LLM_MODEL_NAME",
        description="Model name for chat. Falls back to llm_model_name if not set.",
    )
    chat_llm_base_url: str | None = Field(
        default=None,
        validation_alias="CHAT_LLM_BASE_URL",
        description="Base URL for chat LLM. Falls back to llm_base_url if not set.",
    )
    chat_llm_api_key: str | None = Field(
        default=None,
        validation_alias="CHAT_LLM_API_KEY",
        description="API key for chat LLM. Falls back to llm_api_key if not set.",
    )
    chat_llm_temperature: float = Field(
        default=0.3,
        validation_alias="CHAT_LLM_TEMPERATURE",
        description="Slightly higher temperature for more conversational chat responses.",
    )

    # Chat settings
    chat_max_history_messages: int = Field(
        default=10,
        validation_alias="CHAT_MAX_HISTORY_MESSAGES",
        description="Max recent message pairs to include in context window.",
    )
    chat_max_retrieval_results: int = Field(
        default=10,
        validation_alias="CHAT_MAX_RETRIEVAL_RESULTS",
        description="Max sources to retrieve per query.",
    )
    chat_max_retries: int = Field(
        default=1,
        validation_alias="CHAT_MAX_RETRIES",
        description="Max grounding verification retries.",
    )
    chat_debug: bool = Field(
        default=False,
        validation_alias="CHAT_DEBUG",
        description="Enable verbose debug logging for the entire chat agent chain.",
    )

    # Thinking Mode settings
    chat_default_mode: Literal["quick", "thinking", "deep_thinking"] = Field(
        default="thinking",
        validation_alias="CHAT_DEFAULT_MODE",
        description="Default chat pipeline mode. 'quick' = 4-step, 'thinking' = 5-stage, 'deep_thinking' = thinking + page images.",
    )
    chat_enable_sub_queries: bool = Field(
        default=True,
        validation_alias="CHAT_ENABLE_SUB_QUERIES",
        description="Allow Thinking Mode to decompose complex queries into sub-queries.",
    )
    chat_enable_hyde: bool = Field(
        default=True,
        validation_alias="CHAT_ENABLE_HYDE",
        description="Allow Thinking Mode to generate hypothetical answers for embedding (exploratory only).",
    )
    chat_thinking_max_retrieval_results: int = Field(
        default=15,
        validation_alias="CHAT_THINKING_MAX_RETRIEVAL_RESULTS",
        description="Max sources for Thinking Mode standard retrieval.",
    )
    chat_context_budget_chars: int = Field(
        default=12000,
        validation_alias="CHAT_CONTEXT_BUDGET_CHARS",
        description="Max chars for assembled context in Thinking Mode (~3000 tokens).",
    )
    chat_verification_coverage_threshold: float = Field(
        default=0.7,
        validation_alias="CHAT_VERIFICATION_COVERAGE_THRESHOLD",
        description="Citation coverage ratio below which LLM verification is triggered.",
    )
    chat_verification_relevance_threshold: float = Field(
        default=0.4,
        validation_alias="CHAT_VERIFICATION_RELEVANCE_THRESHOLD",
        description="Avg relevance score below which LLM verification is triggered.",
    )

    # Factual mode optimisation: skip unfiltered seed when NER-filtered results suffice
    chat_factual_skip_unfiltered: bool = Field(
        default=True,
        validation_alias="CHAT_FACTUAL_SKIP_UNFILTERED",
        description="In factual mode with NER filters, skip the unfiltered seed search when filtered results are sufficient.",
    )
    # Deep Thinking Mode settings
    chat_deep_thinking_max_images: int = Field(
        default=5,
        validation_alias="CHAT_DEEP_THINKING_MAX_IMAGES",
        description="Max page images to include in Deep Thinking synthesis prompt.",
    )

    # Agentic retrieval settings (Thinking Mode v2)
    chat_agent_max_iterations: int = Field(
        default=5,
        validation_alias="CHAT_AGENT_MAX_ITERATIONS",
        description="Max tool-calling iterations in the agentic retrieval loop.",
    )
    chat_agent_iteration_timeout_s: float = Field(
        default=30.0,
        validation_alias="CHAT_AGENT_ITERATION_TIMEOUT_S",
        description="Timeout per single iteration (LLM call + tool execution) in seconds.",
    )
    chat_agent_total_timeout_s: float = Field(
        default=120.0,
        validation_alias="CHAT_AGENT_TOTAL_TIMEOUT_S",
        description="Total timeout for the entire agentic retrieval loop.",
    )
    chat_agent_tool_calling_mode: Literal["auto", "native", "react"] = Field(
        default="auto",
        validation_alias="CHAT_AGENT_TOOL_CALLING_MODE",
        description="Tool calling mode: 'auto' picks based on provider, 'native' for OpenAI, 'react' for Ollama.",
    )
    chat_follow_up_context_budget: int = Field(
        default=4000,
        validation_alias="CHAT_FOLLOW_UP_CONTEXT_BUDGET",
        description="Character budget for follow-up conversation context window.",
    )

    # SMILES detection and resolution in chat
    chat_smiles_resolution_enabled: bool = Field(
        default=True,
        validation_alias="CHAT_SMILES_RESOLUTION_ENABLED",
        description="Enable deterministic SMILES detection + compound resolution in chat pipeline.",
    )
    chat_smiles_exact_threshold: float = Field(
        default=0.99,
        ge=0.0,
        le=1.0,
        validation_alias="CHAT_SMILES_EXACT_THRESHOLD",
        description="Cosine similarity threshold for exact SMILES match in chat.",
    )
    chat_smiles_similar_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        validation_alias="CHAT_SMILES_SIMILAR_THRESHOLD",
        description="Cosine similarity threshold for similar SMILES search in chat.",
    )
    chat_smiles_max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        validation_alias="CHAT_SMILES_MAX_RESULTS",
        description="Max compound results per detected SMILES in chat.",
    )

    # Sentinel (AuthZ mode)
    sentinel_url: str = Field(default="http://localhost:9003", validation_alias="SENTINEL_URL")
    sentinel_service_key: str = Field(default="", validation_alias="SENTINEL_SERVICE_KEY")
    sentinel_service_name: str = Field(
        default="docu-store",
        validation_alias="SENTINEL_SERVICE_NAME",
    )
    sentinel_idp_jwks_url: str = Field(
        default="https://www.googleapis.com/oauth2/v3/certs",
        validation_alias="SENTINEL_IDP_JWKS_URL",
    )
    sentinel_cache_ttl: float = Field(
        default=120,
        validation_alias="SENTINEL_CACHE_TTL",
        description="Seconds to cache permission check results (accessible/can). 0 disables.",
    )

    # Browse (tag-based document browser)
    browse_default_category_limit: int = Field(
        default=5,
        validation_alias="BROWSE_DEFAULT_CATEGORY_LIMIT",
    )
    browse_sticky_categories: str = Field(
        default="date,target",
        validation_alias="BROWSE_STICKY_CATEGORIES",
    )

    @property
    def browse_sticky_categories_list(self) -> list[str]:
        if not self.browse_sticky_categories:
            return []
        return [c.strip() for c in self.browse_sticky_categories.split(",") if c.strip()]

    # Ablation / Evaluation toggles
    sparse_encoding_enabled: bool = Field(
        default=False,
        validation_alias="SPARSE_ENCODING_ENABLED",
        description="Enable sparse (TF-IDF) vectors in hybrid search. When False, only dense search is used.",
    )
    chat_enable_entity_accumulation: bool = Field(
        default=True,
        validation_alias="CHAT_ENABLE_ENTITY_ACCUMULATION",
        description="Accumulate NER entities from previous grounded turns for multi-turn continuity.",
    )
    embedding_enable_context_enrichment: bool = Field(
        default=True,
        validation_alias="EMBEDDING_ENABLE_CONTEXT_ENRICHMENT",
        description="Prepend document title/tags/summary context to chunks before dense embedding.",
    )

    # Evaluation (LLM-as-judge)
    eval_judge_provider: Literal["openai", "gemini"] = Field(
        default="openai",
        validation_alias="EVAL_JUDGE_PROVIDER",
        description="LLM provider for evaluation judge.",
    )
    eval_judge_model: str = Field(
        default="gpt-4o",
        validation_alias="EVAL_JUDGE_MODEL",
        description="Model name for evaluation judge.",
    )
    eval_judge_api_key: str | None = Field(
        default=None,
        validation_alias="EVAL_JUDGE_API_KEY",
        description="API key for evaluation judge LLM.",
    )
    eval_judge_temperature: float = Field(
        default=0.0,
        validation_alias="EVAL_JUDGE_TEMPERATURE",
        description="Temperature for evaluation judge (0 for deterministic scoring).",
    )

    # Plugin system
    enabled_plugins: str = Field(
        default="",
        validation_alias="ENABLED_PLUGINS",
        description="Comma-separated list of plugin package names to load.",
    )

    @property
    def enabled_plugins_list(self) -> list[str]:
        """Parse the comma-separated ENABLED_PLUGINS string into a list."""
        if not self.enabled_plugins:
            return []
        return [p.strip() for p in self.enabled_plugins.split(",") if p.strip()]

    plugin_dir: Path = Field(
        default=Path(__file__).resolve().parents[1] / "plugins",
        validation_alias="PLUGIN_DIR",
    )
    plugin_max_concurrent_activities: int = Field(
        default=5,
        validation_alias="PLUGIN_MAX_CONCURRENT_ACTIVITIES",
        description="Max concurrent Temporal activities for all plugin workers.",
    )

    # Request Timing
    enable_request_timing: bool = Field(
        default=True,
        validation_alias="ENABLE_REQUEST_TIMING",
    )
    slow_request_threshold_ms: int = Field(
        default=1000,
        validation_alias="SLOW_REQUEST_THRESHOLD_MS",
    )

    # Prompt management
    prompt_repository_type: Literal["langfuse", "yaml"] = Field(
        default="langfuse",
        validation_alias="PROMPT_REPOSITORY_TYPE",
    )
    langfuse_host: str = Field(
        default="http://localhost:3000",
        validation_alias="LANGFUSE_HOST",
    )
    langfuse_public_key: str | None = Field(
        default=None,
        validation_alias="LANGFUSE_PUBLIC_KEY",
    )
    langfuse_secret_key: str | None = Field(
        default=None,
        validation_alias="LANGFUSE_SECRET_KEY",
    )


# Global settings instance
settings = Settings()
