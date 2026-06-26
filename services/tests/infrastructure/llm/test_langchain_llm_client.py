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
        self.structured_method = method
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
    assert type(fake.last_messages[0]).__name__ == "SystemMessage"


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
    # Adapter injects a top-level "title" (function_calling requires it).
    assert fake.structured_schema == {"title": "response", "type": "object"}
    assert fake.structured_method == "function_calling"


@pytest.mark.asyncio
async def test_complete_structured_preserves_existing_title() -> None:
    client, fake = _client()
    await client.complete_structured("extract", {"title": "Compound", "type": "object"})
    assert fake.structured_schema == {"title": "Compound", "type": "object"}


@pytest.mark.asyncio
async def test_complete_with_image_returns_content() -> None:
    client, _ = _client("caption")
    assert await client.complete_with_image("describe", "aGVsbG8=") == "caption"


def test_image_messages_sniffs_jpeg_mime() -> None:
    import base64

    jpeg_b64 = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 20).decode()
    messages = LangChainLLMClient._image_messages("describe", [jpeg_b64], None)
    url = messages[0].content[1]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")


def test_image_messages_defaults_to_png() -> None:
    import base64

    png_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16).decode()
    messages = LangChainLLMClient._image_messages("describe", [png_b64], None)
    url = messages[0].content[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_get_model_info_reports_provider() -> None:
    client, _ = _client()
    info = await client.get_model_info()
    assert info["provider"] == "ollama"
    assert info["model_name"] == "gemma4:27b"
