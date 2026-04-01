"""Main FastAPI application."""

import contextlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.auth import sentinel
from infrastructure.config import settings
from infrastructure.logging import setup_logging
from interfaces.api.routes.artifact_routes import router as artifact_router
from interfaces.api.routes.browse_routes import router as browse_router
from interfaces.api.routes.chat_routes import router as chat_router
from interfaces.api.routes.dashboard_routes import router as dashboard_router
from interfaces.api.routes.health_routes import router as health_router
from interfaces.api.routes.page_routes import router as page_router
from interfaces.api.routes.search_routes import router as search_router
from interfaces.api.routes.stats_routes import router as stats_router
from interfaces.api.routes.user_routes import router as user_router
from interfaces.api.routes.workspace_routes import router as workspace_router

# Configure structured logging
setup_logging()

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle application startup and shutdown."""
    async with sentinel.lifespan(app):
        logger.info("app_starting", env=settings.app_env)

        # Initialize Qdrant collections on startup
        try:
            from infrastructure.di.container import create_container

            container = create_container()

            from application.ports.vector_store import VectorStore

            vector_store = container[VectorStore]
            await vector_store.ensure_collection_exists()
            logger.info("qdrant_page_collection_initialized")

            from application.ports.compound_vector_store import CompoundVectorStore

            compound_vector_store = container[CompoundVectorStore]
            await compound_vector_store.ensure_compound_collection_exists()
            logger.info("qdrant_compound_collection_initialized")

            from application.ports.summary_vector_store import SummaryVectorStore

            summary_vector_store = container[SummaryVectorStore]
            await summary_vector_store.ensure_collection_exists()
            logger.info("qdrant_summary_collection_initialized")

            # Ensure MongoDB browse indexes
            from application.ports.repositories.tag_browse_read_model import (
                TagBrowseReadModel,
            )

            browse_read_model = container[TagBrowseReadModel]
            await browse_read_model.ensure_browse_indexes()
            logger.info("mongodb_browse_indexes_initialized")

            # Ensure user preferences & activity indexes
            from application.ports.repositories.user_preferences_store import (
                UserPreferencesStore,
            )

            user_store = container[UserPreferencesStore]
            await user_store.ensure_indexes()
            logger.info("mongodb_user_indexes_initialized")

            # Ensure chat indexes
            from application.ports.chat_repository import ChatRepository

            chat_repo = container[ChatRepository]
            await chat_repo.ensure_indexes()
            logger.info("mongodb_chat_indexes_initialized")

            # Ensure workflow status cache indexes
            from application.ports.workflow_status_cache import WorkflowStatusCache

            workflow_cache = container[WorkflowStatusCache]
            await workflow_cache.ensure_indexes()
            logger.info("mongodb_workflow_cache_indexes_initialized")

            # Warm up embedding models so first search request is fast
            from application.ports.embedding_generator import EmbeddingGenerator
            from application.ports.reranker import Reranker
            from infrastructure.embeddings.chemberta_generator import (
                ChemBertaEmbeddingGenerator,
            )

            generator = container[EmbeddingGenerator]
            await generator.get_model_info()
            logger.info("embedding_model_warmed_up")

            chemberta = container[ChemBertaEmbeddingGenerator]
            await chemberta.get_model_info()
            logger.info("chemberta_model_warmed_up")

            reranker = container[Reranker]
            if reranker:
                reranker._ensure_model_loaded()
                logger.info("reranker_model_warmed_up")
        except Exception as e:
            logger.warning("qdrant_initialization_failed", error=str(e))
            # Don't fail startup - embedding features will just be unavailable

        # Ensure heartbeat indexes and start API heartbeat reporter
        import asyncio

        from application.dtos.health_dtos import ModelStatus
        from application.ports.worker_heartbeat_store import WorkerHeartbeatStore
        from infrastructure.health.heartbeat_reader import MongoHeartbeatReader
        from infrastructure.health.heartbeat_reporter import HeartbeatReporter

        heartbeat_task = None
        try:
            # Ensure TTL index
            heartbeat_reader = container[WorkerHeartbeatStore]
            if isinstance(heartbeat_reader, MongoHeartbeatReader):
                await heartbeat_reader.ensure_indexes()

            # Resolve models from container (safe even if warm-up failed above)
            _hb_embedding = container[EmbeddingGenerator]
            _hb_chemberta = container[ChemBertaEmbeddingGenerator]
            _hb_reranker = container[Reranker]

            # Model info providers for the API process
            async def _check_text_embedding() -> ModelStatus:
                info = await _hb_embedding.get_model_info()
                return ModelStatus(
                    name="Text Embedding",
                    loaded=True,
                    device=str(info.get("device", "unknown")),
                    model_name=str(info.get("model_name", "unknown")),
                    inference_ok=True,
                )

            async def _check_chemberta() -> ModelStatus:
                info = await _hb_chemberta.get_model_info()
                return ModelStatus(
                    name="SMILES Embedding (ChemBERTa)",
                    loaded=True,
                    device=str(info.get("device", "unknown")),
                    model_name=str(info.get("model_name", "unknown")),
                    inference_ok=True,
                )

            async def _check_reranker() -> ModelStatus:
                if not settings.reranker_enabled or _hb_reranker is None:
                    return ModelStatus(
                        name="Reranker", loaded=False, device="none", model_name="disabled"
                    )
                return ModelStatus(
                    name="Reranker",
                    loaded=getattr(_hb_reranker, "_model", None) is not None,
                    device=str(getattr(_hb_reranker, "device", settings.reranker_device)),
                    model_name=str(
                        getattr(_hb_reranker, "model_name", settings.reranker_model_name)
                    ),
                    inference_ok=True,
                )

            reporter = HeartbeatReporter(
                mongo_uri=settings.mongo_uri,
                mongo_db=settings.mongo_db,
                worker_type="api_server",
                worker_name="API Server",
                interval_seconds=settings.worker_heartbeat_interval_seconds,
                model_info_providers=[_check_text_embedding, _check_chemberta, _check_reranker],
            )
            heartbeat_task = asyncio.create_task(reporter.run_forever())
            logger.info("api_heartbeat_reporter_started")
        except Exception:
            logger.warning("api_heartbeat_reporter_failed", exc_info=True)

        logger.info("app_ready")

        yield

        # Cleanup
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task
        logger.info("app_shutting_down")
        logger.info("app_stopped")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        description="DocuStore API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Request timing middleware — wraps every request with duration headers + logging
    from interfaces.api.middleware.timing_middleware import TimingMiddleware

    app.add_middleware(TimingMiddleware)

    # Sentinel auth middleware — protects all routes except excluded paths
    # NOTE: Starlette middleware is LIFO — last added runs first.
    # Sentinel must be added BEFORE CORS so that CORS runs first and adds
    # Access-Control-Allow-* headers to ALL responses, including 401s.
    sentinel.protect(app, exclude_paths=["/health", "/docs", "/openapi.json", "/search/health"])

    # CORS middleware — added last so it runs first (wraps everything, including auth errors)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure properly for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(artifact_router)
    app.include_router(browse_router)
    app.include_router(chat_router)
    app.include_router(dashboard_router)
    app.include_router(health_router)
    app.include_router(page_router)
    app.include_router(search_router)
    app.include_router(stats_router)
    app.include_router(user_router)
    app.include_router(workspace_router)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    # Plugin routes — mount dynamically from enabled plugins
    _mount_plugin_routes(app)

    return app


def _mount_plugin_routes(app: FastAPI) -> None:
    """Discover enabled plugins and mount their API routers."""
    try:
        from infrastructure.plugins.context import DefaultPluginContext
        from infrastructure.plugins.loader import discover_plugins

        enabled = settings.enabled_plugins_list
        if not enabled:
            return

        registry = discover_plugins(enabled, settings.plugin_dir)
        if len(registry) == 0:
            return

        # Minimal context for route creation (routes mostly just read from MongoDB)
        context = DefaultPluginContext(
            page_read_model=None,
            artifact_read_model=None,
            smiles_validator=None,
            embedding_generator=None,
            mongo_db=None,
            temporal_client=None,
            plugin_config={},
        )

        for manifest in registry.list_manifests():
            if manifest.has_api_routes and manifest.api_prefix:
                plugin = registry.get_plugin(manifest.name)
                router = plugin.create_router(context)
                if router:
                    app.include_router(router, prefix=manifest.api_prefix, tags=[manifest.name])
                    logger.info(
                        "plugin_router_mounted",
                        plugin=manifest.name,
                        prefix=manifest.api_prefix,
                    )

        # Plugin discovery endpoint
        manifests = registry.list_manifests()

        @app.get("/plugins")
        async def list_plugins() -> list[dict]:
            """List all enabled plugins and their manifests."""
            return [m.model_dump() for m in manifests]

    except Exception:
        logger.warning("plugin_routes_mount_failed", exc_info=True)


# Create app instance
app = create_app()
