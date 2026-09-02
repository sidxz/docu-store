from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
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
    mongo_terms_acceptance_collection: str = Field(
        default="terms_acceptance",
        validation_alias="MONGO_TERMS_ACCEPTANCE_COLLECTION",
    )
    mongo_token_usage_collection: str = Field(
        default="token_usage_events",
        validation_alias="MONGO_TOKEN_USAGE_COLLECTION",
    )
    mongo_token_limits_collection: str = Field(
        default="token_limits",
        validation_alias="MONGO_TOKEN_LIMITS_COLLECTION",
    )
    mongo_user_llm_providers_collection: str = Field(
        default="user_llm_providers",
        validation_alias="MONGO_USER_LLM_PROVIDERS_COLLECTION",
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

    # Worker Heartbeat
    worker_heartbeat_interval_seconds: int = Field(
        default=30,
        validation_alias="WORKER_HEARTBEAT_INTERVAL_SECONDS",
        description="How often each worker writes a heartbeat to MongoDB (seconds).",
    )
    worker_heartbeat_stale_seconds: int = Field(
        default=90,
        validation_alias="WORKER_HEARTBEAT_STALE_SECONDS",
        description="Heartbeats older than this are considered stale/offline.",
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
    # NER LLM (separate from batch LLM — langextract supports ollama/openai/gemini
    # only, NOT anthropic/azure. Each field falls back to the matching llm_* field.
    # If the resolved provider is one langextract can't route, NER degrades to
    # dictionary-only extraction.)
    ner_llm_provider: Literal["ollama", "openai", "gemini"] | None = Field(
        default=None,
        validation_alias="NER_LLM_PROVIDER",
        description="Provider for LLM NER. Falls back to llm_provider. langextract "
        "supports ollama/openai/gemini only; anthropic/azure → dictionary-only NER.",
    )
    ner_llm_model_name: str | None = Field(
        default=None,
        validation_alias="NER_LLM_MODEL_NAME",
        description="Model for LLM NER. Falls back to llm_model_name.",
    )
    ner_llm_base_url: str | None = Field(
        default=None,
        validation_alias="NER_LLM_BASE_URL",
        description="Base URL for Ollama NER. Falls back to llm_base_url. Ignored for cloud providers.",
    )
    ner_llm_api_key: str | None = Field(
        default=None,
        validation_alias="NER_LLM_API_KEY",
        description="API key for cloud NER provider. Falls back to the provider's key / llm_api_key.",
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
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias="ANTHROPIC_API_KEY",
        description="API key for Anthropic (Claude). Used when provider is 'anthropic'.",
    )
    google_api_key: str | None = Field(
        default=None,
        validation_alias="GOOGLE_API_KEY",
        description="API key for Google Gemini. Used when provider is 'gemini'.",
    )
    allow_cloud_llm: bool = Field(
        default=True,
        validation_alias="ALLOW_CLOUD_LLM",
        description=(
            "When False, the LLM layer refuses to construct any cloud provider "
            "(openai/anthropic/gemini) and raises. For confidential / air-gapped "
            "deployments where only local Ollama is permitted."
        ),
    )
    user_llm_keys_enabled: bool = Field(
        default=False,
        validation_alias="USER_LLM_KEYS_ENABLED",
        description=(
            "When True, LLM calls first look up the caller's own provider config "
            "(UserLLMConfigStore) before falling back to the env LLM_* defaults. "
            "Public/BYO-LLM deployments set this; the default keeps today's behavior."
        ),
    )
    user_llm_keys_secret: str | None = Field(
        default=None,
        validation_alias="USER_LLM_KEYS_SECRET",
        description=(
            "Fernet key that encrypts per-user LLM API keys at rest. Required when "
            "USER_LLM_KEYS_ENABLED=true. Generate: python -c 'from cryptography.fernet "
            "import Fernet; print(Fernet.generate_key().decode())'"
        ),
    )
    llm_reasoning: Literal["off", "low", "medium", "high"] = Field(
        default="off",
        validation_alias="LLM_REASONING",
        description="Reasoning/thinking effort for batch LLM. 'off' disables it.",
    )

    @model_validator(mode="after")
    def _require_user_llm_keys_secret(self) -> "Settings":
        """USER_LLM_KEYS_ENABLED=true needs a Fernet key; fail every process at import,
        where the API lifespan's best-effort try/except cannot swallow it.
        """
        if not self.user_llm_keys_enabled:
            return self
        from cryptography.fernet import Fernet

        hint = (
            "python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'"
        )
        if not self.user_llm_keys_secret:
            msg = f"USER_LLM_KEYS_SECRET is required when USER_LLM_KEYS_ENABLED=true. Generate one: {hint}"
            raise ValueError(msg)
        try:
            Fernet(self.user_llm_keys_secret)
        except ValueError as exc:
            msg = f"USER_LLM_KEYS_SECRET is not a valid Fernet key. Generate one: {hint}"
            raise ValueError(msg) from exc
        return self

    # LLM (shared infrastructure — used by summarization and future features)
    llm_provider: Literal["ollama", "openai", "anthropic", "gemini"] = Field(
        default="ollama",
        validation_alias="LLM_PROVIDER",
    )
    llm_model_name: str = Field(
        default="gemma4:31b",
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
    llm_num_ctx: int | None = Field(
        default=32768,
        validation_alias="LLM_NUM_CTX",
        description="Ollama context window (num_ctx). Ollama otherwise defaults to the "
        "model's max context, whose KV cache can exceed VRAM and force slow CPU "
        "offload (e.g. gemma4:31b loads at 256K → 74GB > 48GB A6000). Ignored for "
        "cloud providers. None = let Ollama decide.",
    )

    # Chat LLM (separate from batch LLM — allows different model/temperature for interactive chat)
    chat_llm_provider: Literal["ollama", "openai", "anthropic", "gemini"] | None = Field(
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
    chat_llm_reasoning: Literal["off", "low", "medium", "high"] = Field(
        default="off",
        validation_alias="CHAT_LLM_REASONING",
        description="Reasoning effort for the base/quick-mode chat LLM, and the "
        "inheritance baseline for the synthesis/retrieval knobs. 'off' disables it.",
    )
    chat_synthesis_reasoning: Literal["off", "low", "medium", "high"] | None = Field(
        default=None,
        validation_alias="CHAT_SYNTHESIS_REASONING",
        description="Reasoning effort for the thinking/deep_thinking answer-generation "
        "client (query planning, synthesis, inline verification). None inherits "
        "CHAT_LLM_REASONING. Note: Ollama reasoning is on/off only — the level matters "
        "only for cloud providers.",
    )
    chat_retrieval_reasoning: Literal["off", "low", "medium", "high"] | None = Field(
        default=None,
        validation_alias="CHAT_RETRIEVAL_REASONING",
        description="Reasoning effort for the agentic-retrieval tool-calling client "
        "(thinking/deep_thinking). None inherits CHAT_LLM_REASONING.",
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
    literature_accumulator_budget_chars: int = Field(
        default=1_000_000,
        validation_alias="LITERATURE_ACCUMULATOR_BUDGET_CHARS",
        description=(
            "Retrieval-loop capacity for Literature mode. Separate from the "
            "assembly budget because a literature search accumulates 25-50 full "
            "abstracts per call: charging those against the 12k assembly budget "
            "ends the agentic loop before its second iteration, so the model "
            "never sees a result before choosing its next query. Set high "
            "deliberately — one measured round already reached 173,485 chars, so "
            "anything near that reintroduces the bug. The real bounds on this "
            "loop are chat_agent_max_iterations and the total timeout; this "
            "value is only a runaway backstop. Assembly's own 12k budget still "
            "decides what reaches the answer."
        ),
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

    # Public edition (self-serve signup). Mirrors Duar's SELF_SERVE_ENABLED and
    # the portal's APP_SELF_SERVE_ENABLED. Internal/consortium deployments run
    # with this off and are covered by their own agreements, so the terms gate
    # never fires for them.
    self_serve_enabled: bool = Field(default=False, validation_alias="APP_SELF_SERVE_ENABLED")
    terms_version: str = Field(default="2026-08-28", validation_alias="APP_TERMS_VERSION")

    # Literature search: query Europe PMC and ingest open-licensed papers. Off by
    # default because it puts documents nobody in the workspace vetted into the
    # same corpus the evaluations run against, and because every ingest spends
    # parse, NER, CSER and embedding budget. The portal reads the mirror of this
    # at APP_LITERATURE_ENABLED to decide whether to offer the surface at all.
    literature_enabled: bool = Field(
        default=False,
        validation_alias="LITERATURE_ENABLED",
    )

    # Duar (AuthZ mode)
    duar_url: str = Field(default="http://localhost:9003", validation_alias="DUAR_URL")
    duar_service_key: str = Field(default="", validation_alias="DUAR_SERVICE_KEY")
    duar_service_name: str = Field(
        default="docu-store",
        validation_alias="DUAR_SERVICE_NAME",
    )
    duar_idp_jwks_url: str = Field(
        default="https://www.googleapis.com/oauth2/v3/certs",
        validation_alias="DUAR_IDP_JWKS_URL",
    )
    # Required since Duar 0.11.0 (authz mode): the IdP token's `aud` must
    # equal your OAuth client_id, else a token minted for any other client of
    # the same IdP would authenticate. Without it, Duar(...) raises ValueError.
    duar_idp_audience: str = Field(
        default="",
        validation_alias="DUAR_IDP_AUDIENCE",
    )
    duar_idp_issuer: str = Field(
        default="https://accounts.google.com",
        validation_alias="DUAR_IDP_ISSUER",
    )
    duar_cache_ttl: float = Field(
        default=120,
        validation_alias="DUAR_CACHE_TTL",
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
    chat_clear_ner_filters: bool = Field(
        default=False,
        validation_alias="CHAT_CLEAR_NER_FILTERS",
        description=(
            "Drop extracted entity filters before retrieval, so search is unconstrained. "
            "Ablation of the domain-constraint mechanism."
        ),
    )
    chat_enable_bioactivity_tool: bool = Field(
        default=True,
        validation_alias="CHAT_ENABLE_BIOACTIVITY_TOOL",
        description=(
            "Expose the structured bioactivity lookup (and its deterministic pre-fetch). "
            "When False, quantitative questions must be answered by vector search alone."
        ),
    )
    chat_enable_structure_tool: bool = Field(
        default=True,
        validation_alias="CHAT_ENABLE_STRUCTURE_TOOL",
        description=(
            "Expose chemical-structure lookup over the compound embeddings. "
            "When False, structure-based questions lose their retrieval path."
        ),
    )
    chat_enable_grounding_verification: bool = Field(
        default=True,
        validation_alias="CHAT_ENABLE_GROUNDING_VERIFICATION",
        description="Run inline citation/grounding verification and its retry loop.",
    )
    chat_enable_retrieval: bool = Field(
        default=True,
        validation_alias="CHAT_ENABLE_RETRIEVAL",
        description=(
            "Retrieve context at all. When False the model answers from parametric "
            "memory — the zero-retrieval floor for the ablation study."
        ),
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
