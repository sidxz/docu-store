from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from application.ports.llm_client import LLMClientPort
    from application.ports.prompt_repository import PromptRepositoryPort
    from application.ports.tool_calling_llm import ToolCallingLLMPort
    from infrastructure.config import Settings

log = structlog.get_logger(__name__)


def _make_langfuse_callback_handler(settings: Settings) -> Any | None:
    """Create a Langfuse LangChain CallbackHandler for LLM tracing (v3 SDK).

    Returns None (with a warning) if Langfuse credentials are missing or
    the langfuse package is not installed.
    """
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None
    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler

        # Initialise the global Langfuse singleton so CallbackHandler() can pick
        # up the credentials — pydantic-settings does not populate os.environ.
        Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        handler = CallbackHandler()
    except Exception as exc:
        log.warning("llm.factory.langfuse_tracing_unavailable", error=str(exc))
        return None
    else:
        log.info("llm.factory.langfuse_tracing_enabled", host=settings.langfuse_host)
        return handler


def _resolve_api_key(provider: str, settings: Settings) -> str | None:
    """Pick the per-provider API key, falling back to the generic LLM_API_KEY."""
    if provider == "openai":
        return settings.openai_api_key or settings.llm_api_key
    if provider == "anthropic":
        return settings.anthropic_api_key or settings.llm_api_key
    if provider == "gemini":
        return settings.google_api_key or settings.llm_api_key
    return None  # ollama — no key


def create_llm_client(settings: Settings) -> LLMClientPort:
    """Instantiate the LLM adapter selected by LLM_PROVIDER in config."""
    from infrastructure.llm.adapters.langchain_llm_client import LangChainLLMClient

    provider = settings.llm_provider
    api_key = _resolve_api_key(provider, settings)
    if provider != "ollama" and not settings.allow_cloud_llm:
        msg = f"Cloud LLM provider {provider!r} is disabled (ALLOW_CLOUD_LLM=false)."
        raise ValueError(msg)
    if provider != "ollama" and not api_key:
        msg = f"No API key configured for cloud provider {provider!r}. Set the provider's API key or LLM_API_KEY."
        raise ValueError(msg)
    log.info("llm.factory", provider=provider, model=settings.llm_model_name)
    return LangChainLLMClient(
        provider=provider,
        model_name=settings.llm_model_name,
        temperature=settings.llm_temperature,
        api_key=api_key,
        base_url=settings.llm_base_url,
        reasoning=settings.llm_reasoning,
        allow_cloud=settings.allow_cloud_llm,
        lane=None,
        langfuse_handler=_make_langfuse_callback_handler(settings),
    )


def create_chat_llm_client(settings: Settings, *, reasoning: str | None = None, lane: str = "base") -> LLMClientPort:
    """Instantiate a chat LLM client, falling back to batch LLM settings.

    ``reasoning`` overrides the reasoning effort for this client; when None it
    uses ``chat_llm_reasoning``. The container passes a resolved value to build
    the separate thinking-mode synthesis client.
    """
    from infrastructure.llm.adapters.langchain_llm_client import LangChainLLMClient

    provider = settings.chat_llm_provider or settings.llm_provider
    model = settings.chat_llm_model_name or settings.llm_model_name
    base_url = settings.chat_llm_base_url or settings.llm_base_url
    # Chat key: explicit chat key → per-provider key → generic.
    api_key = (
        None
        if provider == "ollama"
        else (settings.chat_llm_api_key or _resolve_api_key(provider, settings))
    )
    if provider != "ollama" and not settings.allow_cloud_llm:
        msg = f"Cloud LLM provider {provider!r} is disabled (ALLOW_CLOUD_LLM=false)."
        raise ValueError(msg)
    if provider != "ollama" and not api_key:
        msg = f"No API key configured for cloud chat provider {provider!r}. Set CHAT_LLM_API_KEY or the provider's API key or LLM_API_KEY."
        raise ValueError(msg)
    log.info("llm.factory.chat", provider=provider, model=model)
    return LangChainLLMClient(
        provider=provider,
        model_name=model,
        temperature=settings.chat_llm_temperature,
        api_key=api_key,
        base_url=base_url,
        reasoning=reasoning if reasoning is not None else settings.chat_llm_reasoning,
        allow_cloud=settings.allow_cloud_llm,
        lane=lane,
        langfuse_handler=_make_langfuse_callback_handler(settings),
    )


def create_tool_calling_llm_client(settings: Settings) -> ToolCallingLLMPort:
    """Instantiate a tool-calling LLM adapter for the agentic retrieval loop.

    Uses the same provider/model as the chat LLM. Mode selection:
    - "auto"/"native": native bind_tools() for all providers
    - "react": ReAct text parsing for models without native tool support
    """
    from infrastructure.llm.adapters.tool_calling_adapter import (
        NativeToolCallingAdapter,
        ReactToolCallingAdapter,
    )

    effective_provider = settings.chat_llm_provider or settings.llm_provider
    effective_model = settings.chat_llm_model_name or settings.llm_model_name
    effective_base_url = settings.chat_llm_base_url or settings.llm_base_url
    effective_api_key = (
        None
        if effective_provider == "ollama"
        else (settings.chat_llm_api_key or _resolve_api_key(effective_provider, settings))
    )
    effective_temperature = settings.chat_llm_temperature
    mode = settings.chat_agent_tool_calling_mode

    if effective_provider != "ollama" and not settings.allow_cloud_llm:
        msg = f"Cloud LLM provider {effective_provider!r} is disabled (ALLOW_CLOUD_LLM=false)."
        raise ValueError(msg)

    # Native tool calling for all providers (modern Ollama models support it).
    # ReAct is an explicit opt-in for old local models that lack native tools.
    use_native = mode != "react"

    log.info(
        "llm.factory.tool_calling",
        provider=effective_provider,
        model=effective_model,
        mode=mode,
        use_native=use_native,
    )

    langfuse_handler = _make_langfuse_callback_handler(settings)

    if use_native:
        return NativeToolCallingAdapter(
            provider=effective_provider,
            model_name=effective_model,
            api_key=effective_api_key,
            base_url=effective_base_url,
            temperature=effective_temperature,
            reasoning=settings.chat_retrieval_reasoning or settings.chat_llm_reasoning,
            allow_cloud=settings.allow_cloud_llm,
            lane="retrieval",
            langfuse_handler=langfuse_handler,
        )

    return ReactToolCallingAdapter(
        provider=effective_provider,
        model_name=effective_model,
        api_key=effective_api_key,
        base_url=effective_base_url,
        temperature=effective_temperature,
        reasoning=settings.chat_llm_reasoning,
        allow_cloud=settings.allow_cloud_llm,
        lane="retrieval",
        langfuse_handler=langfuse_handler,
    )


def create_prompt_repository(settings: Settings) -> PromptRepositoryPort:
    """Instantiate the prompt repository selected by PROMPT_REPOSITORY_TYPE in config."""
    repo_type = settings.prompt_repository_type

    if repo_type == "yaml":
        from infrastructure.llm.prompt_repositories.yaml_prompt_repository import (
            YamlPromptRepository,
        )

        log.info("prompt_repo.factory", type="yaml")
        return YamlPromptRepository()

    if repo_type == "langfuse":
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            msg = (
                "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set when "
                "PROMPT_REPOSITORY_TYPE=langfuse. "
                "Set PROMPT_REPOSITORY_TYPE=yaml to use local YAML fallback."
            )
            raise ValueError(msg)
        from infrastructure.llm.prompt_repositories.langfuse_prompt_repository import (
            LangfusePromptRepository,
        )

        log.info("prompt_repo.factory", type="langfuse", host=settings.langfuse_host)
        return LangfusePromptRepository(
            host=settings.langfuse_host,
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
        )

    msg = f"Unsupported PROMPT_REPOSITORY_TYPE: {repo_type!r}. Valid options: yaml, langfuse"
    raise ValueError(msg)
