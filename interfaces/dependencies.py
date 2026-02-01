"""FastAPI dependency injection integration with Lagom."""

from functools import lru_cache

from lagom import Container

from infrastructure.di.container import create_container


@lru_cache
def get_container() -> Container:
    """Get the DI container instance.

    Cached to ensure singleton behavior across requests.
    """
    return create_container()
