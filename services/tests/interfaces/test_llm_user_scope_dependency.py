"""The chat-send route resolves the caller's LLM config into the request context,
and the background run (create_task inside the endpoint) inherits it."""

from __future__ import annotations

import asyncio
import contextlib
from uuid import UUID

from fastapi import params

from application.ports.user_llm_config import UserLLMConfig
from application.services.llm_scope import UserLLMScope
from infrastructure.llm.llm_context import get_user_config
from interfaces.dependencies import llm_user_scope
from tests.fakes.fake_auth import FakeAuth

CFG = UserLLMConfig(provider="openai", api_key="k")


class _Store:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID]] = []

    async def get(self, workspace_id: UUID, user_id: UUID) -> UserLLMConfig | None:
        self.calls.append((workspace_id, user_id))
        return CFG


async def _read() -> UserLLMConfig | None:
    return get_user_config()


async def test_dependency_scopes_config_to_the_request_and_its_tasks() -> None:
    auth, store = FakeAuth(), _Store()
    container = {UserLLMScope: UserLLMScope(store, enabled=True)}

    dep = llm_user_scope(auth=auth, container=container)
    await anext(dep)  # dependency entered — the endpoint body runs here
    assert get_user_config() is CFG
    task = asyncio.create_task(_read())  # what ChatRunRegistry.start() does
    with contextlib.suppress(StopAsyncIteration):
        await anext(dep)  # teardown
    assert get_user_config() is None
    assert await task is CFG
    assert store.calls == [(auth.workspace_id, auth.user_id)]


def test_send_message_route_declares_the_dependency() -> None:
    from interfaces.api.routes.chat_routes import router

    route = next(
        r for r in router.routes
        if r.path.endswith("/{conversation_id}/messages") and "POST" in r.methods
    )
    calls = [d.call for d in route.dependant.dependencies]
    assert llm_user_scope in calls
    # sanity: the decorator form registers a Depends, not a positional param
    assert all(isinstance(d, params.Depends) for d in route.dependencies)
