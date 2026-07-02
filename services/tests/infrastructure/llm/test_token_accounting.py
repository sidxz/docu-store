"""Token accounting via a LangChain callback.

The callback is the single collection point for LLM usage: attached at every
adapter's call config, it feeds the request-scoped ``TokenCounter`` so that
*every* provider/path (base client, structured output, agentic tool loop) is
counted — instead of scattered ``record_usage`` calls that missed the tool loop.
"""

from __future__ import annotations

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult, LLMResult

from infrastructure.llm.adapters.tool_calling_adapter import NativeToolCallingAdapter
from infrastructure.llm.token_counter import (
    TokenCounter,
    TokenCountingCallbackHandler,
    extract_usage_from_llm_result,
)


def _result(prompt: int, completion: int) -> LLMResult:
    msg = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": prompt,
            "output_tokens": completion,
            "total_tokens": prompt + completion,
        },
    )
    return LLMResult(generations=[[ChatGeneration(message=msg)]])


class _FakeUsageChatModel(BaseChatModel):
    """Minimal chat model that reports fixed usage — fires on_llm_end."""

    prompt: int = 0
    completion: int = 0

    @property
    def _llm_type(self) -> str:
        return "fake-usage"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        msg = AIMessage(
            content="done",
            usage_metadata={
                "input_tokens": self.prompt,
                "output_tokens": self.completion,
                "total_tokens": self.prompt + self.completion,
            },
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN201
        return self


def test_extract_usage_from_llm_result_reads_usage_metadata() -> None:
    assert extract_usage_from_llm_result(_result(100, 40)) == (100, 40)


def test_extract_usage_from_llm_result_falls_back_to_llm_output() -> None:
    result = LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content="x"))]],
        llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 4}},
    )
    assert extract_usage_from_llm_result(result) == (10, 4)


@pytest.mark.asyncio
async def test_handler_records_onto_active_counter() -> None:
    counter = TokenCounter()
    with counter:
        await TokenCountingCallbackHandler().on_llm_end(_result(100, 40))
    assert counter.prompt_tokens == 100
    assert counter.completion_tokens == 40


@pytest.mark.asyncio
async def test_handler_accumulates_across_calls() -> None:
    handler = TokenCountingCallbackHandler()
    counter = TokenCounter()
    with counter:
        await handler.on_llm_end(_result(100, 40))
        await handler.on_llm_end(_result(200, 60))
    assert counter.prompt_tokens == 300
    assert counter.completion_tokens == 100


@pytest.mark.asyncio
async def test_handler_noop_without_active_counter() -> None:
    # No active counter — must be a silent no-op, not an error.
    await TokenCountingCallbackHandler().on_llm_end(_result(5, 2))


@pytest.mark.asyncio
async def test_native_tool_adapter_counts_via_callback(monkeypatch) -> None:
    """The agentic retrieval loop was the uncounted path — it must count now."""
    fake = _FakeUsageChatModel(prompt=500, completion=120)
    adapter = NativeToolCallingAdapter(provider="ollama", model_name="x")
    monkeypatch.setattr(adapter, "_get_llm", lambda: fake)
    counter = TokenCounter()
    with counter:
        await adapter.invoke_with_tools([{"role": "user", "content": "hi"}], tools=[])
    assert counter.prompt_tokens == 500
    assert counter.completion_tokens == 120
