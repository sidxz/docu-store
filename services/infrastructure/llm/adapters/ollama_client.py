from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from langchain_ollama import ChatOllama

log = structlog.get_logger(__name__)


class OllamaLLMClient:
    """LLMClientPort adapter backed by a local Ollama server via LangChain.

    Lazy-loads langchain_ollama to avoid import cost in processes that don't
    need LLM functionality (e.g. read_worker).
    """

    def __init__(
        self,
        model_name: str = "gemma3:27b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.1,
        langfuse_handler: Any | None = None,
    ) -> None:
        self._model_name = model_name
        self._base_url = base_url
        self._temperature = temperature
        self._langfuse_handler = langfuse_handler
        self._llm: ChatOllama | None = None

    def _get_llm(self) -> ChatOllama:
        if self._llm is None:
            from langchain_ollama import ChatOllama  # noqa: PLC0415

            self._llm = ChatOllama(
                model=self._model_name,
                base_url=self._base_url,
                temperature=self._temperature,
            )
        return self._llm

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
    ) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

        llm = self._get_llm()
        if temperature is not None:
            llm = llm.bind(temperature=temperature)

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        log.debug("ollama.complete", model=self._model_name, prompt_len=len(prompt))
        config = {"callbacks": [self._langfuse_handler]} if self._langfuse_handler else {}
        response = await llm.ainvoke(messages, config=config)
        return str(response.content)

    async def complete_with_image(
        self,
        prompt: str,
        image_b64: str,
        *,
        system_prompt: str | None = None,
    ) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

        llm = self._get_llm()

        image_content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_b64}"},
            },
        ]

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=image_content))

        log.debug(
            "ollama.complete_with_image",
            model=self._model_name,
            prompt_len=len(prompt),
            image_b64_len=len(image_b64),
        )
        config = {"callbacks": [self._langfuse_handler]} if self._langfuse_handler else {}
        response = await llm.ainvoke(messages, config=config)
        return str(response.content)

    async def get_model_info(self) -> dict[str, str]:
        return {"provider": "ollama", "model_name": self._model_name, "base_url": self._base_url}
