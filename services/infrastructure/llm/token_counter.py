"""Token usage accumulator using contextvars.

Usage in agents:
    from infrastructure.llm.token_counter import TokenCounter

    counter = TokenCounter()
    with counter:
        # All LLM calls inside this block accumulate into `counter`
        await llm.complete(...)
        async for token in llm.stream(...):
            ...
    print(counter.prompt_tokens, counter.completion_tokens, counter.total_tokens)

The LLM adapters (OpenAI, Ollama) automatically detect and update the
active counter via the `_active_counter` contextvar.
"""

from __future__ import annotations

from contextvars import ContextVar
from types import TracebackType

from langchain_core.callbacks import AsyncCallbackHandler

_active_counter: ContextVar[TokenCounter | None] = ContextVar("_active_counter", default=None)


class TokenCounter:
    """Accumulates prompt/completion token counts across multiple LLM calls."""

    __slots__ = ("_token", "completion_tokens", "prompt_tokens", "total_tokens")

    def __init__(self) -> None:
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0
        self._token = None

    def add(self, prompt: int, completion: int) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion

    def __enter__(self) -> TokenCounter:
        self._token = _active_counter.set(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._token is not None:
            _active_counter.reset(self._token)
            self._token = None


def get_active_counter() -> TokenCounter | None:
    """Return the active counter for the current context, or None."""
    return _active_counter.get()


def record_usage(prompt: int, completion: int) -> None:
    """Record token usage on the active counter, if any."""
    counter = _active_counter.get()
    if counter is not None:
        counter.add(prompt, completion)


def extract_usage_from_response(response: object) -> tuple[int, int]:
    """Extract (prompt, completion) token counts from a LangChain AIMessage.

    Checks ``usage_metadata`` first (LangChain ≥0.2 standard), then falls back
    to ``response_metadata`` (OpenAI-style ``token_usage`` / ``usage`` dicts).
    """
    meta = getattr(response, "usage_metadata", None)
    if meta:
        return int(meta.get("input_tokens", 0)), int(meta.get("output_tokens", 0))
    # Fallback: response_metadata from OpenAI
    rm = getattr(response, "response_metadata", {})
    usage = rm.get("token_usage") or rm.get("usage", {})
    if usage:
        return int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
    return 0, 0


def extract_usage_from_llm_result(result: object) -> tuple[int, int]:
    """Extract (prompt, completion) token counts from a LangChain ``LLMResult``.

    This is the shape delivered to ``on_llm_end``. Reads each generation's
    message ``usage_metadata`` first, then falls back to the provider
    ``llm_output`` (OpenAI-style ``token_usage``/``usage``).
    """
    for gens in getattr(result, "generations", None) or []:
        for gen in gens:
            message = getattr(gen, "message", None)
            if message is not None:
                prompt, completion = extract_usage_from_response(message)
                if prompt or completion:
                    return prompt, completion
    out = getattr(result, "llm_output", None) or {}
    if isinstance(out, dict):
        usage = out.get("token_usage") or out.get("usage") or {}
        if usage:
            return (
                int(usage.get("prompt_tokens", usage.get("input_tokens", 0))),
                int(usage.get("completion_tokens", usage.get("output_tokens", 0))),
            )
    return 0, 0


class TokenCountingCallbackHandler(AsyncCallbackHandler):
    """Feeds every LLM call's usage into the active ``TokenCounter``.

    Attached at each adapter's call config alongside the Langfuse handler, so
    all providers and paths (base client, structured output, agentic tool loop)
    are counted from one place. It is a no-op outside a ``with TokenCounter()``
    scope, so non-chat callers (ingestion, NER) are unaffected. Async so it runs
    in the request's context and sees the ``_active_counter`` contextvar.
    """

    async def on_llm_end(self, response: object, **kwargs: object) -> None:
        prompt, completion = extract_usage_from_llm_result(response)
        if prompt or completion:
            record_usage(prompt, completion)


# Stateless (reads the contextvar) — one shared instance is safe across requests.
_token_counting_handler = TokenCountingCallbackHandler()


def callbacks_for(langfuse_handler: object | None = None) -> list:
    """Callbacks for an LLM call: always the token counter, plus Langfuse if on."""
    callbacks: list = [_token_counting_handler]
    if langfuse_handler is not None:
        callbacks.append(langfuse_handler)
    return callbacks
