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
    """Accumulates prompt/completion token counts across multiple LLM calls.

    Optional identity fields attribute the scope's work: they feed Langfuse
    trace metadata (via ``call_config``) and let the owner of the scope write
    a ledger event afterwards. Identity-less counters behave exactly as before.
    """

    __slots__ = (
        "_token",
        "completion_tokens",
        "models",
        "prompt_tokens",
        "session_id",
        "tags",
        "total_tokens",
        "user_id",
        "workspace_id",
    )

    def __init__(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        workspace_id: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0
        self.models: list[str] = []
        self._token = None
        self.user_id = user_id
        self.session_id = session_id
        self.workspace_id = workspace_id
        self.tags = tags

    def add(self, prompt: int, completion: int, model: str | None = None) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion
        if model and model not in self.models:
            self.models.append(model)

    @property
    def model(self) -> str | None:
        """Which model did the work, in the order the scope reached for them.

        Joined when a scope used more than one — a chat turn can route a cheap
        model at one stage and the answer model at another — because picking one
        to name would be a guess about which tokens belong to which.
        """
        return ", ".join(self.models) or None

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


def record_usage(prompt: int, completion: int, model: str | None = None) -> None:
    """Record token usage on the active counter, if any."""
    counter = _active_counter.get()
    if counter is not None:
        counter.add(prompt, completion, model)


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


def extract_model_from_llm_result(result: object) -> str | None:
    """The model name a LangChain ``LLMResult`` reports, if it reports one.

    Providers disagree on where it lives: OpenAI-compatible ones put
    ``model_name`` in ``llm_output``, Ollama puts ``model`` in the message's
    ``response_metadata``. The name is the *resolved* one, so an OpenRouter
    route answers with the id it actually served.
    """
    out = getattr(result, "llm_output", None) or {}
    if isinstance(out, dict):
        name = out.get("model_name") or out.get("model")
        if name:
            return str(name)
    for gens in getattr(result, "generations", None) or []:
        for gen in gens:
            meta = getattr(getattr(gen, "message", None), "response_metadata", None) or {}
            name = meta.get("model_name") or meta.get("model")
            if name:
                return str(name)
    return None


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
            record_usage(prompt, completion, extract_model_from_llm_result(response))


# Stateless (reads the contextvar) — one shared instance is safe across requests.
_token_counting_handler = TokenCountingCallbackHandler()


def callbacks_for(langfuse_handler: object | None = None) -> list:
    """Callbacks for an LLM call: always the token counter, plus Langfuse if on."""
    callbacks: list = [_token_counting_handler]
    if langfuse_handler is not None:
        callbacks.append(langfuse_handler)
    return callbacks


def call_config(langfuse_handler: object | None = None) -> dict:
    """LangChain call config: counting+tracing callbacks, plus Langfuse v3
    trace attribution (``langfuse_*`` metadata keys) when the active counter
    carries identity. The single construction point for every adapter.
    """
    config: dict = {"callbacks": callbacks_for(langfuse_handler)}
    counter = _active_counter.get()
    if counter is None:
        return config
    metadata: dict = {}
    if counter.user_id:
        metadata["langfuse_user_id"] = counter.user_id
    if counter.session_id:
        metadata["langfuse_session_id"] = counter.session_id
    if counter.tags:
        metadata["langfuse_tags"] = list(counter.tags)
    if counter.workspace_id:
        metadata["workspace_id"] = counter.workspace_id
    if metadata:
        config["metadata"] = metadata
    return config
