"""Application configuration using Pydantic Settings."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "DocuStore"
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    # EventStoreDB
    eventstoredb_uri: str = "esdb://localhost:2113?tls=false"

    # Kafka
    enable_external_event_streaming: bool = True
    kafka_bootstrap_servers: str = "localhost:19092"
    kafka_topic: str = "docu_store_events"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # MongoDB Read Models
    mongo_uri: str = "mongodb://localhost:27017/?replicaSet=rs0&directConnection=true"
    mongo_db: str = "docu_store"
    mongo_pages_collection: str = "page_read_models"
    mongo_artifacts_collection: str = "artifact_read_models"
    mongo_tracking_collection: str = "read_model_tracking"


# Global settings instance
settings = Settings()
