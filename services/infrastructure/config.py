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

    # Embeddings
    embedding_model_provider: Literal["sentence-transformers", "openai"] = Field(
        default="sentence-transformers",
        validation_alias="EMBEDDING_MODEL_PROVIDER",
    )
    embedding_model_name: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        validation_alias="EMBEDDING_MODEL_NAME",
    )
    embedding_device: Literal["cpu", "cuda", "mps"] = Field(
        default="cpu",
        validation_alias="EMBEDDING_DEVICE",
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
