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
    # For OpenAI (when provider is "openai")
    openai_api_key: str | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )


# Global settings instance
settings = Settings()
