from __future__ import annotations

import pytest

from infrastructure.llm.adapters.langchain_llm_client import LangChainLLMClient


class _FakeAIMessage:
    def __init__(self, content: str) -> None:
        self.content = content
        self.usage_metadata = {"input_tokens": 3, "output_tokens": 5}
        self.response_metadata: dict = {}


class _FakeStructured:
    async def ainvoke(self, messages, config=None):  # noqa: ANN001, ARG002
        return {"name": "acetone", "formula": "C3H6O"}


class _FakeChatModel:
    def __init__(self, content: str = "hello") -> None:
        self._content = content
        self.bind_calls: list[dict] = []

    async def ainvoke(self, messages, config=None):  # noqa: ANN001, ARG002
        self.last_messages = messages
        return _FakeAIMessage(self._content)

    async def astream(self, messages, config=None):  # noqa: ANN001, ARG002
        for piece in ("he", "llo"):
            yield _FakeAIMessage(piece)

    def bind(self, **kwargs):  # noqa: ANN003
        self.bind_calls.append(kwargs)
        return self

    def with_structured_output(self, schema, method=None):  # noqa: ANN001, ARG002
        self.structured_schema = schema
        return _FakeStructured()


def _client(content: str = "hello") -> tuple[LangChainLLMClient, _FakeChatModel]:
    fake = _FakeChatModel(content)
    client = LangChainLLMClient(
        provider="ollama", model_name="gemma4:27b", chat_model=fake,
    )
    return client, fake


@pytest.mark.asyncio
async def test_complete_returns_content() -> None:
    client, _ = _client("the answer")
    assert await client.complete("q") == "the answer"


@pytest.mark.asyncio
async def test_complete_passes_system_prompt() -> None:
    client, fake = _client()
    await client.complete("q", system_prompt="be terse")
    # System message first, human message second.
    assert len(fake.last_messages) == 2


@pytest.mark.asyncio
async def test_stream_yields_token_deltas() -> None:
    client, _ = _client()
    chunks = [c async for c in client.stream("q")]
    assert "".join(chunks) == "hello"


@pytest.mark.asyncio
async def test_complete_structured_returns_dict() -> None:
    client, fake = _client()
    out = await client.complete_structured("extract", {"type": "object"})
    assert out == {"name": "acetone", "formula": "C3H6O"}
    assert fake.structured_schema == {"type": "object"}


@pytest.mark.asyncio
async def test_complete_with_image_returns_content() -> None:
    client, _ = _client("caption")
    assert await client.complete_with_image("describe", "aGVsbG8=") == "caption"


@pytest.mark.asyncio
async def test_get_model_info_reports_provider() -> None:
    client, _ = _client()
    info = await client.get_model_info()
    assert info["provider"] == "ollama"
    assert info["model_name"] == "gemma4:27b"
