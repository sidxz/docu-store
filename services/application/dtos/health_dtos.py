"""DTOs for the system health endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SystemInfo(BaseModel):
    app_version: str
    python_version: str
    os_info: str
    hostname: str
    uptime_seconds: float
    timestamp: str  # ISO format


class GpuDevice(BaseModel):
    index: int
    name: str
    memory_total_mb: int
    memory_used_mb: int
    memory_free_mb: int


class GpuInfo(BaseModel):
    cuda_available: bool
    mps_available: bool
    cuda_version: str | None = None
    device_count: int = 0
    devices: list[GpuDevice] = []


class ServiceStatus(BaseModel):
    name: str
    status: Literal["healthy", "unhealthy", "degraded", "disabled"]
    latency_ms: float | None = None
    version: str | None = None
    error: str | None = None
    details: dict | None = None


class ModelStatus(BaseModel):
    name: str
    loaded: bool
    device: str  # "cpu" | "cuda" | "mps"
    model_name: str
    inference_ok: bool | None = None
    error: str | None = None


class ConfigSummary(BaseModel):
    app_env: str
    llm_provider: str
    llm_model: str
    chat_llm_provider: str
    chat_llm_model: str
    embedding_model: str
    embedding_device: str
    smiles_model: str
    smiles_device: str
    reranker_enabled: bool
    reranker_model: str | None = None
    reranker_device: str | None = None
    kafka_enabled: bool
    temporal_address: str
    temporal_max_concurrent_activities: int
    temporal_max_concurrent_llm_activities: int
    qdrant_url: str
    blob_base_url: str


class WorkerHeartbeat(BaseModel):
    """Status snapshot from a single worker process."""

    worker_id: str  # "{worker_type}:{hostname}:{pid}"
    worker_type: (
        str  # api_server, temporal_cpu, temporal_llm, pipeline, read_projector, plugin_consumer
    )
    worker_name: str  # Human-readable label
    hostname: str
    pid: int
    status: Literal["online", "offline"]  # Computed by reader from staleness
    gpu: GpuInfo
    loaded_models: list[ModelStatus] = []
    system: SystemInfo
    started_at: str  # ISO timestamp
    last_heartbeat: str  # ISO timestamp


class DetailedHealthResponse(BaseModel):
    overall_status: Literal["healthy", "degraded", "unhealthy"]
    system: SystemInfo
    gpu: GpuInfo
    services: list[ServiceStatus]
    models: list[ModelStatus]
    config: ConfigSummary
    workers: list[WorkerHeartbeat] = []
    checked_at: str  # ISO timestamp


class BulkWorkflowResponse(BaseModel):
    """Response for bulk workflow trigger operations."""

    triggered: int
    workflow_ids: list[str]
