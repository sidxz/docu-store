from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, Literal

import structlog

from infrastructure.llm.token_counter import extract_usage_from_response, record_usage

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

log = structlog.get_logger(__name__)

# Magic-byte prefixes → MIME, for the data: URLs cloud vision APIs validate.
_IMAGE_MAGIC = ((b"\x89PNG", "image/png"), (b"\xff\xd8\xff", "image/jpeg"), (b"GIF8", "image/gif"))


def _sniff_image_mime(image_b64: str) -> str:
    """Detect an image's MIME from its base64 header; default to PNG.

    Anthropic/Gemini reject a data: URL whose declared type mismatches the bytes,
    so we can't hardcode image/png. 24 base64 chars decode to 18 bytes — enough
    for every magic number below, including WebP's RIFF/WEBP at offset 8.
    """
    import base64

    try:
        head = base64.b64decode(image_b64[:24])
    except Exception:  # malformed input falls back to the default
        return "image/png"
    for magic, mime in _IMAGE_MAGIC:
        if head.startswith(magic):
            return mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


class LangChainLLMClient:
    """Provider-agnostic ``LLMClientPort`` adapter backed by a LangChain model.

    The chat model is built lazily via ``build_chat_model`` (or injected via
    ``chat_model`` for tests), so processes that never call the LLM pay no
    construction cost.
    """

    def __init__(
        self,
        *,
        provider: str,
        model_name: str,
        temperature: float = 0.1,
        api_key: str | None = None,
        base_url: str | None = None,
        reasoning: str | None = None,
        allow_cloud: bool = False,
        lane: str | None = None,
        langfuse_handler: Any | None = None,
        chat_model: BaseChatModel | None = None,
    ) -> None:
        self._provider = provider
        self._model_name = model_name
        self._temperature = temperature
        self._api_key = api_key
        self._base_url = base_url
        self._reasoning = reasoning
        self._allow_cloud = allow_cloud
        self._lane = lane
        self._langfuse_handler = langfuse_handler
        self._injected = chat_model
        self._models: dict[str, Any] = {}

    def _get_llm(self) -> BaseChatModel:
        if self._injected is not None:
            return self._injected
        from infrastructure.llm.model_builder import build_chat_model
        from infrastructure.llm.reasoning_context import get_lane_override

        level = get_lane_override(self._lane) or self._reasoning
        key = level or "off"
        if key not in self._models:
            self._models[key] = build_chat_model(
                provider=self._provider,
                model_name=self._model_name,
                temperature=self._temperature,
                api_key=self._api_key,
                base_url=self._base_url,
                reasoning=level,
                allow_cloud=self._allow_cloud,
            )
        return self._models[key]

    def _config(self) -> dict:
        return {"callbacks": [self._langfuse_handler]} if self._langfuse_handler else {}

    @staticmethod
    def _text_messages(prompt: str, system_prompt: str | None) -> list:
        from langchain_core.messages import HumanMessage, SystemMessage

        messages: list = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        return messages

    @staticmethod
    def _image_messages(prompt: str, images_b64: list[str], system_prompt: str | None) -> list:
        from langchain_core.messages import HumanMessage, SystemMessage

        content: list[dict] = [{"type": "text", "text": prompt}]
        for img in images_b64:
            mime = _sniff_image_mime(img)
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img}"}},
            )
        messages: list = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=content))
        return messages

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
    ) -> str:
        llm = self._get_llm()
        if temperature is not None:
            llm = llm.bind(temperature=temperature)
        response = await llm.ainvoke(self._text_messages(prompt, system_prompt), config=self._config())
        record_usage(*extract_usage_from_response(response))
        return str(response.content)

    async def stream_with_reasoning(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        images_b64: list[str] | None = None,
    ) -> AsyncGenerator[tuple[Literal["content", "reasoning"], str], None]:
        llm = self._get_llm()
        if temperature is not None:
            llm = llm.bind(temperature=temperature)
        messages = (
            self._image_messages(prompt, images_b64, system_prompt)
            if images_b64
            else self._text_messages(prompt, system_prompt)
        )
        last_chunk = None
        async for chunk in llm.astream(messages, config=self._config()):
            last_chunk = chunk
            reasoning = chunk.additional_kwargs.get("reasoning_content")
            if reasoning:
                yield ("reasoning", str(reasoning))
            if chunk.content:
                yield ("content", str(chunk.content))
        if last_chunk is not None:
            record_usage(*extract_usage_from_response(last_chunk))

    async def stream(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        images_b64: list[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        async for kind, text in self.stream_with_reasoning(
            prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            images_b64=images_b64,
        ):
            if kind == "content":
                yield text

    async def complete_with_image(
        self,
        prompt: str,
        image_b64: str,
        *,
        system_prompt: str | None = None,
    ) -> str:
        llm = self._get_llm()
        messages = self._image_messages(prompt, [image_b64], system_prompt)
        response = await llm.ainvoke(messages, config=self._config())
        record_usage(*extract_usage_from_response(response))
        return str(response.content)

    async def complete_structured(
        self,
        prompt: str,
        schema: dict,
        *,
        system_prompt: str | None = None,
    ) -> dict:
        # function_calling derives the tool name from the schema's top-level "title";
        # without it LangChain raises "Unsupported function ... must have a top-level
        # 'title' key". Inject a default so callers needn't carry boilerplate titles.
        if isinstance(schema, dict) and "title" not in schema:
            schema = {"title": "response", **schema}
        # function_calling is the portable method across ollama/openai/anthropic/gemini.
        llm = self._get_llm().with_structured_output(schema, method="function_calling")
        result = await llm.ainvoke(
            self._text_messages(prompt, system_prompt), config=self._config(),
        )
        # ponytail: structured-output usage isn't surfaced by LangChain here.
        if hasattr(result, "model_dump"):
            return result.model_dump()
        return dict(result)

    async def get_model_info(self) -> dict[str, str]:
        return {"provider": self._provider, "model_name": self._model_name}
