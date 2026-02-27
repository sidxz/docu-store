from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from application.ports.llm_client import LLMClientPort
    from application.ports.prompt_repository import PromptRepositoryPort
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
        from langfuse import Langfuse  # noqa: PLC0415
        from langfuse.langchain import CallbackHandler  # noqa: PLC0415

        # Initialise the global Langfuse singleton so CallbackHandler() can pick
        # up the credentials — pydantic-settings does not populate os.environ.
        Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        handler = CallbackHandler()
        log.info("llm.factory.langfuse_tracing_enabled", host=settings.langfuse_host)
        return handler
    except Exception as exc:
        log.warning("llm.factory.langfuse_tracing_unavailable", error=str(exc))
        return None


def create_llm_client(settings: Settings) -> LLMClientPort:
    """Instantiate the LLM adapter selected by LLM_PROVIDER in config."""
    provider = settings.llm_provider

    if provider == "ollama":
        from infrastructure.llm.adapters.ollama_client import OllamaLLMClient  # noqa: PLC0415

        log.info("llm.factory", provider="ollama", model=settings.llm_model_name)
        return OllamaLLMClient(
            model_name=settings.llm_model_name,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
            langfuse_handler=_make_langfuse_callback_handler(settings),
        )

    if provider == "openai":
        from infrastructure.llm.adapters.openai_client import OpenAILLMClient  # noqa: PLC0415

        if not settings.llm_api_key and not settings.openai_api_key:
            msg = "LLM_API_KEY or OPENAI_API_KEY must be set when LLM_PROVIDER=openai"
            raise ValueError(msg)
        log.info("llm.factory", provider="openai", model=settings.llm_model_name)
        return OpenAILLMClient(
            model_name=settings.llm_model_name,
            api_key=settings.llm_api_key or settings.openai_api_key,
            temperature=settings.llm_temperature,
        )

    msg = f"Unsupported LLM_PROVIDER: {provider!r}. Valid options: ollama, openai"
    raise ValueError(msg)


def create_prompt_repository(settings: Settings) -> PromptRepositoryPort:
    """Instantiate the prompt repository selected by PROMPT_REPOSITORY_TYPE in config."""
    repo_type = settings.prompt_repository_type

    if repo_type == "yaml":
        from infrastructure.llm.prompt_repositories.yaml_prompt_repository import (  # noqa: PLC0415
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
        from infrastructure.llm.prompt_repositories.langfuse_prompt_repository import (  # noqa: PLC0415
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
