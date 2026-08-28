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
    extract_model_from_llm_result,
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


from infrastructure.llm.token_counter import call_config


def test_call_config_includes_langfuse_metadata_from_active_counter() -> None:
    counter = TokenCounter(
        user_id="u-1", session_id="conv-1", workspace_id="ws-1", tags=["chat"],
    )
    with counter:
        cfg = call_config(None)
    assert cfg["metadata"] == {
        "langfuse_user_id": "u-1",
        "langfuse_session_id": "conv-1",
        "langfuse_tags": ["chat"],
        "workspace_id": "ws-1",
    }


def test_call_config_omits_metadata_without_identity() -> None:
    with TokenCounter():  # anonymous counter (identity-less)
        assert "metadata" not in call_config(None)
    assert "metadata" not in call_config(None)  # no active counter at all


def test_call_config_keeps_token_and_langfuse_handlers() -> None:
    sentinel = object()
    cfg = call_config(sentinel)
    assert sentinel in cfg["callbacks"]
    assert any(isinstance(cb, TokenCountingCallbackHandler) for cb in cfg["callbacks"])


# ── Which model actually answered, alongside how much it cost ──


def _result_with_model(prompt: int, completion: int, *, llm_output=None, meta=None) -> LLMResult:
    msg = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": prompt,
            "output_tokens": completion,
            "total_tokens": prompt + completion,
        },
        response_metadata=meta or {},
    )
    return LLMResult(generations=[[ChatGeneration(message=msg)]], llm_output=llm_output)


def test_model_name_is_read_from_either_place_providers_put_it() -> None:
    """OpenAI-compatible providers use llm_output.model_name; Ollama uses the
    message's response_metadata.model."""
    assert (
        extract_model_from_llm_result(
            _result_with_model(1, 1, llm_output={"model_name": "gpt-5.6-luna"})
        )
        == "gpt-5.6-luna"
    )
    assert (
        extract_model_from_llm_result(_result_with_model(1, 1, meta={"model": "gemma3:27b"}))
        == "gemma3:27b"
    )
    assert extract_model_from_llm_result(_result_with_model(1, 1)) is None


async def test_the_counter_records_what_answered_not_just_how_much() -> None:
    handler = TokenCountingCallbackHandler()
    with TokenCounter() as counter:
        await handler.on_llm_end(_result_with_model(10, 5, llm_output={"model_name": "gpt-5.4"}))

    assert counter.model == "gpt-5.4"
    assert counter.total_tokens == 15


async def test_a_turn_using_two_models_names_both() -> None:
    """Naming one of them would be a guess about which tokens were whose."""
    handler = TokenCountingCallbackHandler()
    with TokenCounter() as counter:
        await handler.on_llm_end(_result_with_model(10, 5, llm_output={"model_name": "gpt-5.4-mini"}))
        await handler.on_llm_end(_result_with_model(90, 40, llm_output={"model_name": "gpt-5.6-luna"}))
        await handler.on_llm_end(_result_with_model(5, 5, llm_output={"model_name": "gpt-5.4-mini"}))

    assert counter.model == "gpt-5.4-mini, gpt-5.6-luna"  # deduped, first use first
    assert counter.total_tokens == 155


async def test_a_provider_that_reports_no_model_leaves_it_unset() -> None:
    handler = TokenCountingCallbackHandler()
    with TokenCounter() as counter:
        await handler.on_llm_end(_result(10, 5))

    assert counter.model is None
    assert counter.total_tokens == 15
