"""FastAPI dependency injection integration with Lagom."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from duar_auth import RequestAuth
from fastapi import Depends
from lagom import Container

from infrastructure.auth import duar
from infrastructure.di.container import create_container

get_auth = duar.get_auth


@lru_cache
def get_container() -> Container:
    """Get the DI container instance.

    Cached to ensure singleton behavior across requests.
    """
    return create_container()


async def llm_user_scope(
    auth: Annotated[RequestAuth, Depends(get_auth)],
    container: Annotated[Container, Depends(get_container)],
) -> AsyncIterator[None]:
    """Resolve the caller's LLM config for this request — and for the chat run it
    spawns (``registry.start`` → ``create_task`` copies this context).

    Must stay an *async* dependency: sync ones run in a threadpool and the
    contextvar never reaches the endpoint. Not middleware: BaseHTTPMiddleware
    runs downstream in another task.
    """
    from application.services.llm_scope import UserLLMScope

    async with container[UserLLMScope].for_user(auth.workspace_id, auth.user_id):
        yield
