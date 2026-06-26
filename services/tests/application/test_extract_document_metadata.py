from __future__ import annotations

import pytest

from application.use_cases.extract_document_metadata_use_case import (
    ExtractDocumentMetadataUseCase,
)


class _StubPromptRepo:
    async def render_prompt(self, name: str, **kwargs: str) -> str:  # noqa: ARG002
        return "rendered prompt"


class _StubLLM:
    def __init__(self) -> None:
        self.schema: dict | None = None

    async def complete_structured(self, prompt: str, schema: dict, **kwargs) -> dict:  # noqa: ANN003, ARG002
        self.schema = schema
        return {"title": "Inhibitor study", "authors": [{"name": "A. Smith"}], "date": "2024"}


@pytest.mark.asyncio
async def test_llm_extract_uses_structured_output() -> None:
    # Construct without __init__ — _llm_extract only touches these two deps.
    uc = object.__new__(ExtractDocumentMetadataUseCase)
    uc.prompt_repository = _StubPromptRepo()
    uc.llm_client = _StubLLM()

    out = await uc._llm_extract("some page text")

    assert out == {"title": "Inhibitor study", "authors": [{"name": "A. Smith"}], "date": "2024"}
    # Passed a JSON-schema dict (not a free-text "respond in JSON" prompt).
    assert uc.llm_client.schema["type"] == "object"
    assert "authors" in uc.llm_client.schema["properties"]


@pytest.mark.asyncio
async def test_llm_extract_swallows_errors() -> None:
    class _Boom:
        async def complete_structured(self, *a, **k):  # noqa: ANN002, ANN003
            raise RuntimeError("provider down")

    uc = object.__new__(ExtractDocumentMetadataUseCase)
    uc.prompt_repository = _StubPromptRepo()
    uc.llm_client = _Boom()

    assert await uc._llm_extract("text") is None
