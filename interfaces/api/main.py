"""Main FastAPI application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.config import settings
from interfaces.api.routes.artifact_routes import router as artifact_router
from interfaces.api.routes.page_routes import router as page_router
from interfaces.dependencies import get_container

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle application startup and shutdown."""
    logger.info("app_starting", env=settings.app_env)

    # Initialize Kafka publisher
    container = get_container()
    # mongo_client = AsyncIOMotorClient(settings.mongo_uri, tz_aware=True)
    # container[AsyncIOMotorClient] = mongo_client
    # app.state.mongo_client = mongo_client

    logger.info("app_ready")

    yield

    # Cleanup
    logger.info("app_shutting_down")
    # app.state.mongo_client.close()
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

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


# Create app instance
app = create_app()
