"""API route registrations."""

from interfaces.api.routes.page_routes import router as page_router

router = page_router

__all__ = ["router"]
