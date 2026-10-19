"""Infrastructure adapter for comprehensive health checking.

Implements the SystemHealthChecker port by probing concrete services
(MongoDB, Qdrant, Temporal, etc.) and ML models.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import structlog

from application.dtos.health_dtos import (
    ConfigSummary,
    DetailedHealthResponse,
    ModelStatus,
    ServiceStatus,
)
from infrastructure.health.gpu_info import get_gpu_info, get_system_info

if TYPE_CHECKING:
    from uuid import UUID

    from motor.motor_asyncio import AsyncIOMotorClient

    from application.ports.compound_vector_store import CompoundVectorStore
    from application.ports.embedding_generator import EmbeddingGenerator
    from application.ports.reranker import Reranker
    from application.ports.summary_vector_store import SummaryVectorStore
    from application.ports.user_llm_config import UserLLMConfigStore
    from application.ports.vector_store import VectorStore
    from application.ports.worker_heartbeat_store import WorkerHeartbeatStore
    from infrastructure.config import Settings
    from infrastructure.embeddings.chemberta_generator import ChemBertaEmbeddingGenerator

logger = structlog.get_logger()

_START_TIME = time.monotonic()

_CHECK_TIMEOUT = 3.0  # seconds per individual check

# Core services — if any is down the system is "unhealthy"
_CORE_SERVICES = frozenset({"MongoDB", "EventStoreDB", "Qdrant", "Temporal"})


class InfrastructureHealthChecker:
    """Concrete health checker that probes all infrastructure dependencies.

    All dependencies are constructor-injected — no service-locator /
    container lookups at check time.
    """

    def __init__(
        self,
        *,
        mongo_client: AsyncIOMotorClient,
        vector_store: VectorStore,
        compound_vector_store: CompoundVectorStore,
        summary_vector_store: SummaryVectorStore,
        embedding_generator: EmbeddingGenerator,
        chemberta_generator: ChemBertaEmbeddingGenerator,
        reranker: Reranker | None,
        heartbeat_store: WorkerHeartbeatStore,
        settings: Settings,
        llm_store: UserLLMConfigStore | None = None,
    ) -> None:
        self._mongo = mongo_client
        self._vector_store = vector_store
        self._compound_vector_store = compound_vector_store
        self._summary_vector_store = summary_vector_store
        self._embedding_generator = embedding_generator
        self._chemberta = chemberta_generator
        self._reranker = reranker
        self._heartbeat_store = heartbeat_store
        self._settings = settings
        self._llm_store = llm_store

    # ------------------------------------------------------------------
    # Port implementation
    # ------------------------------------------------------------------

    async def run_checks(self, workspace_id: UUID | None = None) -> DetailedHealthResponse:
        """Run all health checks concurrently and return a consolidated report."""
        now = datetime.now(tz=UTC)

        system_info = get_system_info(_START_TIME, now)
        gpu_info = get_gpu_info()
        config_summary = self._get_config_summary()

        service_results, model_results, workers = await asyncio.gather(
            self._check_all_services(workspace_id),
            self._check_all_models(),
            self._heartbeat_store.get_all_workers(),
        )

        overall = _compute_overall_status(service_results, model_results)

        return DetailedHealthResponse(
            overall_status=overall,
            system=system_info,
            gpu=gpu_info,
            services=service_results,
            models=model_results,
            config=config_summary,
            workers=workers,
            checked_at=now.isoformat(),
        )

    # ------------------------------------------------------------------
    # Config summary (no secrets)
    # ------------------------------------------------------------------

    def _get_config_summary(self) -> ConfigSummary:
        s = self._settings
        return ConfigSummary(
            app_env=s.app_env,
            llm_provider=s.llm_provider,
            llm_model=s.llm_model_name,
            chat_llm_provider=s.chat_llm_provider or s.llm_provider,
            chat_llm_model=s.chat_llm_model_name or s.llm_model_name,
            embedding_model=s.embedding_model_name,
            embedding_device=s.embedding_device,
            smiles_model=s.smiles_embedding_model_name,
            smiles_device=s.smiles_embedding_device,
            reranker_enabled=s.reranker_enabled,
            reranker_model=s.reranker_model_name if s.reranker_enabled else None,
            reranker_device=s.reranker_device if s.reranker_enabled else None,
            kafka_enabled=s.enable_external_event_streaming,
            temporal_max_concurrent_activities=s.temporal_max_concurrent_activities,
            temporal_max_concurrent_llm_activities=s.temporal_max_concurrent_llm_activities,
        )

    # ------------------------------------------------------------------
    # Service checks
    # ------------------------------------------------------------------

    async def _check_all_services(self, workspace_id: UUID | None) -> list[ServiceStatus]:
        s = self._settings
        checks: list[asyncio.Task[ServiceStatus]] = [
            _timed_check("MongoDB", self._check_mongodb()),
            _timed_check("EventStoreDB", self._check_eventstoredb()),
            _timed_check("Qdrant", self._check_qdrant(workspace_id)),
            _timed_check("Temporal", self._check_temporal()),
            _timed_check("LLM Service", self._check_llm(workspace_id)),
            _timed_check("Duar", self._check_duar()),
            _timed_check("Langfuse", self._check_langfuse()),
            _timed_check("Blob Storage", self._check_blob_storage()),
        ]

        if s.enable_external_event_streaming:
            checks.append(_timed_check("Kafka", self._check_kafka()))
        else:
            checks.append(_make_disabled_status("Kafka"))

        return list(await asyncio.gather(*checks))

    async def _check_mongodb(self) -> ServiceStatus:
        await self._mongo.admin.command("ping")

        details: dict = {}
        try:
            rs_status = await self._mongo.admin.command("replSetGetStatus")
            details["replica_set"] = rs_status.get("set", "unknown")
            members = rs_status.get("members", [])
            details["members"] = len(members)
            details["has_primary"] = any(m.get("stateStr") == "PRIMARY" for m in members)
        except Exception:
            details["replica_set"] = "unavailable"

        server_info = await self._mongo.server_info()
        return ServiceStatus(
            name="MongoDB",
            status="healthy",
            version=server_info.get("version"),
            details=details,
        )

    async def _check_eventstoredb(self) -> ServiceStatus:
        import httpx

        parsed = urlparse(self._settings.eventstoredb_uri)
        host = parsed.hostname or "localhost"
        port = parsed.port or 2113
        url = f"http://{host}:{port}/health/live"

        async with httpx.AsyncClient(timeout=_CHECK_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        return ServiceStatus(name="EventStoreDB", status="healthy")

    async def _check_qdrant(self, workspace_id: UUID | None) -> ServiceStatus:
        # Collections are shared by every workspace: report only the caller's
        # vectors, never the platform's totals.
        if workspace_id is None:
            await self._vector_store.get_collection_info()
            return ServiceStatus(name="Qdrant", status="healthy")
        stores = {
            "page_embeddings": self._vector_store,
            "compound_embeddings": self._compound_vector_store,
            "summary_embeddings": self._summary_vector_store,
        }
        return ServiceStatus(
            name="Qdrant",
            status="healthy",
            details={
                "collections": {
                    name: {"points_count": await store.count_vectors(workspace_id)}
                    for name, store in stores.items()
                },
            },
        )

    async def _check_temporal(self) -> ServiceStatus:
        from temporalio.client import Client

        client = await Client.connect(self._settings.temporal_address)
        details: dict = {}

        try:
            tq = await client.workflow_service.describe_task_queue(
                namespace="default",
                task_queue={"name": "artifact_processing"},
            )
            details["artifact_processing_pollers"] = (
                len(tq.pollers) if hasattr(tq, "pollers") else 0
            )
        except Exception:
            details["artifact_processing_pollers"] = "unavailable"

        try:
            tq_llm = await client.workflow_service.describe_task_queue(
                namespace="default",
                task_queue={"name": self._settings.temporal_llm_task_queue},
            )
            details["llm_processing_pollers"] = (
                len(tq_llm.pollers) if hasattr(tq_llm, "pollers") else 0
            )
        except Exception:
            details["llm_processing_pollers"] = "unavailable"

        return ServiceStatus(name="Temporal", status="healthy", details=details)

    async def _check_kafka(self) -> ServiceStatus:
        bootstrap = self._settings.kafka_bootstrap_servers

        def _sync_check() -> dict:
            from confluent_kafka.admin import AdminClient

            admin = AdminClient({"bootstrap.servers": bootstrap})
            metadata = admin.list_topics(timeout=_CHECK_TIMEOUT)
            brokers = list(metadata.brokers.values())
            topics = [t for t in metadata.topics if not t.startswith("_")]
            return {"brokers": len(brokers), "topics": topics}

        details = await asyncio.to_thread(_sync_check)
        return ServiceStatus(name="Kafka", status="healthy", details=details)

    async def _check_llm(self, workspace_id: UUID | None) -> ServiceStatus:
        import httpx

        s = self._settings
        if s.user_llm_keys_enabled and self._llm_store is not None:
            # Each workspace runs on its own provider; the server's LLM_* is unused.
            entry = await self._llm_store.get_entry(workspace_id) if workspace_id else None
            return ServiceStatus(
                name="LLM Service",
                status="healthy" if entry else "degraded",
                details={
                    "provider": entry.provider,
                    "configured_model": entry.model,
                    "chat_model": entry.chat_model,
                    "api_key_set": True,
                    "key_source": "workspace",
                }
                if entry
                else {"key_source": "workspace"},
                error=None
                if entry
                else "No AI provider connected: add one under Settings → AI Provider",
            )
        if s.llm_provider == "ollama":
            url = f"{s.llm_base_url}/api/tags"
            async with httpx.AsyncClient(timeout=_CHECK_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

            model_names = [m.get("name", "") for m in data.get("models", [])]
            model_available = any(s.llm_model_name in n for n in model_names)

            return ServiceStatus(
                name="LLM Service",
                status="healthy" if model_available else "degraded",
                details={
                    "provider": "ollama",
                    "configured_model": s.llm_model_name,
                    "model_available": model_available,
                    "available_models": model_names[:10],
                },
                error=f"Model '{s.llm_model_name}' not found in Ollama"
                if not model_available
                else None,
            )
        # Cloud providers — report config (API key presence)
        has_key = bool(s.llm_api_key)
        return ServiceStatus(
            name="LLM Service",
            status="healthy" if has_key else "degraded",
            details={
                "provider": s.llm_provider,
                "configured_model": s.llm_model_name,
                "api_key_set": has_key,
            },
            error="LLM API key not configured" if not has_key else None,
        )

    async def _check_duar(self) -> ServiceStatus:
        import httpx

        url = f"{self._settings.duar_url}/health"
        async with httpx.AsyncClient(timeout=_CHECK_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        return ServiceStatus(name="Duar", status="healthy")

    async def _check_langfuse(self) -> ServiceStatus:
        if self._settings.prompt_repository_type != "langfuse":
            return ServiceStatus(name="Langfuse", status="disabled")

        import httpx

        url = f"{self._settings.langfuse_host}/api/public/health"
        async with httpx.AsyncClient(timeout=_CHECK_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        return ServiceStatus(name="Langfuse", status="healthy")

    async def _check_blob_storage(self) -> ServiceStatus:
        import fsspec

        parsed = urlparse(self._settings.blob_base_url)
        scheme = parsed.scheme or "file"

        try:
            fs = fsspec.filesystem(scheme, **(self._settings.blob_storage_options or {}))
            if scheme == "file":
                path = parsed.path
                exists = await asyncio.to_thread(fs.exists, path)
                return ServiceStatus(
                    name="Blob Storage",
                    status="healthy" if exists else "degraded",
                    details={"scheme": scheme, "exists": exists},
                    error="Blob directory does not exist" if not exists else None,
                )
            # S3/GCS — try listing root
            await asyncio.to_thread(fs.ls, parsed.path, detail=False)
            return ServiceStatus(
                name="Blob Storage",
                status="healthy",
                details={"scheme": scheme},
            )
        except Exception as e:
            return ServiceStatus(
                name="Blob Storage",
                status="unhealthy",
                error=str(e),
                details={"scheme": scheme},
            )

    # ------------------------------------------------------------------
    # Model checks
    # ------------------------------------------------------------------

    async def _check_all_models(self) -> list[ModelStatus]:
        checks = [
            self._check_text_embedding(),
            self._check_smiles_embedding(),
            self._check_reranker(),
        ]
        return list(await asyncio.gather(*checks, return_exceptions=False))

    async def _check_text_embedding(self) -> ModelStatus:
        try:
            info = await self._embedding_generator.get_model_info()
            return ModelStatus(
                name="Text Embedding",
                loaded=True,
                device=str(info.get("device", "unknown")),
                model_name=str(info.get("model_name", "unknown")),
                inference_ok=True,
            )
        except Exception as e:
            return ModelStatus(
                name="Text Embedding",
                loaded=False,
                device=self._settings.embedding_device,
                model_name=self._settings.embedding_model_name,
                inference_ok=False,
                error=str(e),
            )

    async def _check_smiles_embedding(self) -> ModelStatus:
        try:
            info = await self._chemberta.get_model_info()
            return ModelStatus(
                name="SMILES Embedding (ChemBERTa)",
                loaded=True,
                device=str(info.get("device", "unknown")),
                model_name=str(info.get("model_name", "unknown")),
                inference_ok=True,
            )
        except Exception as e:
            return ModelStatus(
                name="SMILES Embedding (ChemBERTa)",
                loaded=False,
                device=self._settings.smiles_embedding_device,
                model_name=self._settings.smiles_embedding_model_name,
                inference_ok=False,
                error=str(e),
            )

    async def _check_reranker(self) -> ModelStatus:
        if not self._settings.reranker_enabled or self._reranker is None:
            return ModelStatus(
                name="Reranker",
                loaded=False,
                device="none",
                model_name="disabled",
            )

        try:
            model_name = getattr(self._reranker, "model_name", self._settings.reranker_model_name)
            device = getattr(self._reranker, "device", self._settings.reranker_device)
            loaded = getattr(self._reranker, "_model", None) is not None
            return ModelStatus(
                name="Reranker",
                loaded=loaded,
                device=str(device),
                model_name=str(model_name),
                inference_ok=loaded or None,
            )
        except Exception as e:
            return ModelStatus(
                name="Reranker",
                loaded=False,
                device=self._settings.reranker_device,
                model_name=self._settings.reranker_model_name,
                inference_ok=False,
                error=str(e),
            )


# ---------------------------------------------------------------------------
# Pure functions (no instance state needed)
# ---------------------------------------------------------------------------


async def _timed_check(name: str, coro: object) -> ServiceStatus:
    """Run a single service check with a timeout wrapper."""
    t0 = time.monotonic()
    try:
        result = await asyncio.wait_for(coro, timeout=_CHECK_TIMEOUT)  # type: ignore[arg-type]
        latency = round((time.monotonic() - t0) * 1000, 1)
        if isinstance(result, ServiceStatus):
            result.latency_ms = latency
            return result
        return ServiceStatus(name=name, status="healthy", latency_ms=latency, details=result)
    except TimeoutError:
        return ServiceStatus(
            name=name,
            status="unhealthy",
            latency_ms=round((time.monotonic() - t0) * 1000, 1),
            error="Health check timed out",
        )
    except Exception as e:
        return ServiceStatus(
            name=name,
            status="unhealthy",
            latency_ms=round((time.monotonic() - t0) * 1000, 1),
            error=str(e),
        )


async def _make_disabled_status(name: str) -> ServiceStatus:
    return ServiceStatus(name=name, status="disabled")


def _compute_overall_status(
    services: list[ServiceStatus],
    models: list[ModelStatus],
) -> str:
    core_unhealthy = any(s.status == "unhealthy" for s in services if s.name in _CORE_SERVICES)
    if core_unhealthy:
        return "unhealthy"

    any_model_failed = any(m.inference_ok is False for m in models if m.model_name != "disabled")
    any_service_unhealthy = any(s.status == "unhealthy" for s in services)

    if any_model_failed or any_service_unhealthy:
        return "degraded"

    any_degraded = any(s.status == "degraded" for s in services)
    if any_degraded:
        return "degraded"

    return "healthy"
