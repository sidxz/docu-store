"""API middleware for error handling and cross-cutting concerns."""

from interfaces.api.middleware.error_handler import handle_use_case_errors

__all__ = ["handle_use_case_errors"]
