"""Main FastAPI application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.config import settings
from infrastructure.logging import setup_logging
from interfaces.api.routes.artifact_routes import router as artifact_router
from interfaces.api.routes.page_routes import router as page_router
from interfaces.api.routes.search_routes import router as search_router

# Configure structured logging
setup_logging()

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ARG001
    """Handle application startup and shutdown."""
    logger.info("app_starting", env=settings.app_env)

    # Initialize Qdrant collection on startup
    try:
        from infrastructure.di.container import create_container  # noqa: PLC0415

        container = create_container()
        from application.ports.vector_store import VectorStore  # noqa: PLC0415

        vector_store = container[VectorStore]
        await vector_store.ensure_collection_exists()
        logger.info("qdrant_collection_initialized")
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

    # Include routers
    app.include_router(artifact_router)
    app.include_router(page_router)
    app.include_router(search_router)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


# Create app instance
app = create_app()
