"""SendMessageUseCase must write exactly one ledger event per run —
including error and client-disconnect paths (holes 2+3 of the audit)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from application.dtos.chat_dtos import AgentEvent, ChatMessageDTO, ConversationDTO
from application.use_cases.chat_use_cases import SendMessageUseCase
from infrastructure.llm.token_counter import record_usage


def _conversation(conversation_id, workspace_id, owner_id) -> ConversationDTO:
    now = datetime.now(UTC)
    return ConversationDTO(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        owner_id=owner_id,
        title="t",
        folder_id=None,
        created_at=now,
        updated_at=now,
        message_count=0,
        model_used=None,
        is_archived=False,
    )


class FakeChatRepo:
    def __init__(self, conversation: ConversationDTO) -> None:
        self._conversation = conversation
        self.messages: list[ChatMessageDTO] = []

    async def get_conversation(self, conversation_id, workspace_id=None, owner_id=None):
        return self._conversation

    async def append_message(self, message):
        self.messages.append(message)
        return message

    async def update_conversation(self, conversation_id, **kwargs):
        return True

    async def get_recent_messages(self, conversation_id, limit=10):
        return []


class FakeUsageStore:
    def __init__(self) -> None:
        self.events = []

    async def record(self, event) -> None:
        self.events.append(event)


class FakeAgent:
    """Simulates the LLM pipeline: records usage onto the ambient counter
    (exactly what the real adapters' on_llm_end callback does), then yields."""

    def __init__(self, *, usage=(100, 20), fail=False, hang=False) -> None:
        self._usage = usage
        self._fail = fail
        self._hang = hang
        self.message_id = uuid4()

    async def run(self, **kwargs):
        if self._usage:
            record_usage(*self._usage)
        yield AgentEvent(type="step_started", step="s1", description="d")
        if self._fail:
            raise RuntimeError("pipeline blew up")
        if self._hang:
            yield AgentEvent(type="step_completed", step="s1", status="completed")
            return
        yield AgentEvent(type="token", delta="answer")
        yield AgentEvent(
            type="done",
            message_id=self.message_id,
            total_tokens=120,
            prompt_tokens=100,
            completion_tokens=20,
            duration_ms=5,
        )


def _use_case(agent, store):
    ws, owner, conv = uuid4(), uuid4(), uuid4()
    repo = FakeChatRepo(_conversation(conv, ws, owner))
    uc = SendMessageUseCase(
        chat_repository=repo, chat_agent=agent, token_usage_store=store,
    )
    return uc, repo, ws, owner, conv


@pytest.mark.asyncio
async def test_success_writes_one_attributed_chat_event() -> None:
    store = FakeUsageStore()
    agent = FakeAgent()
    uc, repo, ws, owner, conv = _use_case(agent, store)

    events = [
        e async for e in uc.execute(
            conversation_id=conv, workspace_id=ws, owner_id=owner, message="hi",
        )
    ]

    assert any(e.type == "done" for e in events)
    assert len(store.events) == 1
    ev = store.events[0]
    assert (ev.workspace_id, ev.user_id) == (ws, owner)
    assert (ev.kind, ev.source) == ("chat", "chat_message")
    assert (ev.prompt, ev.completion, ev.total) == (100, 20, 120)
    assert ev.ref == str(conv)
    assert ev.event_id == f"chat:{agent.message_id}"


@pytest.mark.asyncio
async def test_agent_exception_still_records_partial_usage() -> None:
    store = FakeUsageStore()
    uc, repo, ws, owner, conv = _use_case(FakeAgent(fail=True), store)

    with pytest.raises(RuntimeError):
        async for _ in uc.execute(
            conversation_id=conv, workspace_id=ws, owner_id=owner, message="hi",
        ):
            pass

    assert len(store.events) == 1
    assert store.events[0].total == 120
    assert store.events[0].event_id is None  # no done event -> no message id


@pytest.mark.asyncio
async def test_client_disconnect_still_records_usage() -> None:
    store = FakeUsageStore()
    uc, repo, ws, owner, conv = _use_case(FakeAgent(hang=True), store)

    gen = uc.execute(conversation_id=conv, workspace_id=ws, owner_id=owner, message="hi")
    await gen.__anext__()  # consume one event, then the client goes away
    await gen.aclose()

    assert len(store.events) == 1
    assert store.events[0].total == 120


@pytest.mark.asyncio
async def test_zero_usage_records_nothing() -> None:
    store = FakeUsageStore()
    uc, repo, ws, owner, conv = _use_case(FakeAgent(usage=None), store)

    async for _ in uc.execute(
        conversation_id=conv, workspace_id=ws, owner_id=owner, message="hi",
    ):
        pass

    assert store.events == []
