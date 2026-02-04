"""API route registrations."""

from interfaces.api.routes.artifact_routes import router as artifact_router
from interfaces.api.routes.page_routes import router as page_router

__all__ = ["artifact_router", "page_router"]
