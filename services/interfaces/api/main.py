"""Main FastAPI application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.auth import sentinel
from infrastructure.config import settings
from infrastructure.logging import setup_logging
from interfaces.api.routes.artifact_routes import router as artifact_router
from interfaces.api.routes.page_routes import router as page_router
from interfaces.api.routes.search_routes import router as search_router
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
            from infrastructure.di.container import create_container  # noqa: PLC0415

            container = create_container()

            from application.ports.vector_store import VectorStore  # noqa: PLC0415

            vector_store = container[VectorStore]
            await vector_store.ensure_collection_exists()
            logger.info("qdrant_page_collection_initialized")

            from application.ports.compound_vector_store import CompoundVectorStore  # noqa: PLC0415

            compound_vector_store = container[CompoundVectorStore]
            await compound_vector_store.ensure_compound_collection_exists()
            logger.info("qdrant_compound_collection_initialized")

            from application.ports.summary_vector_store import SummaryVectorStore  # noqa: PLC0415

            summary_vector_store = container[SummaryVectorStore]
            await summary_vector_store.ensure_collection_exists()
            logger.info("qdrant_summary_collection_initialized")
        except Exception as e:  # noqa: BLE001
            logger.warning("qdrant_initialization_failed", error=str(e))
            # Don't fail startup - embedding features will just be unavailable

        logger.info("app_ready")

        yield

        # Cleanup
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

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure properly for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Sentinel auth middleware — protects all routes except excluded paths
    sentinel.protect(app, exclude_paths=["/health", "/docs", "/openapi.json", "/search/health"])

    # Include routers
    app.include_router(artifact_router)
    app.include_router(page_router)
    app.include_router(search_router)
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
        from infrastructure.plugins.context import DefaultPluginContext  # noqa: PLC0415
        from infrastructure.plugins.loader import discover_plugins  # noqa: PLC0415

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

    except Exception:  # noqa: BLE001
        logger.warning("plugin_routes_mount_failed", exc_info=True)


# Create app instance
app = create_app()
