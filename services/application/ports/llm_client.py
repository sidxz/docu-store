from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Protocol


class LLMClientPort(Protocol):
    """Port for making LLM inference calls.

    Provider-agnostic interface. Concrete adapters live in
    infrastructure/llm/adapters/ and implement Ollama, OpenAI, Gemini, etc.

    Following the Ports & Adapters pattern from Clean Architecture.
    """

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Send a text prompt and return the model's response.

        Args:
            prompt: The user prompt to send to the model
            system_prompt: Optional system/instruction prompt
            temperature: Override instance temperature for this call

        Returns:
            The model's text response

        Raises:
            RuntimeError: If the LLM call fails or times out

        """
        ...

    async def stream(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        images_b64: list[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens one by one from the model.

        Args:
            prompt: The user prompt to send to the model
            system_prompt: Optional system/instruction prompt
            temperature: Override instance temperature for this call
            images_b64: Optional list of base64-encoded images (PNG/JPEG) for multimodal prompting

        Yields:
            String token deltas as they are generated

        Raises:
            RuntimeError: If the LLM call fails or times out

        """
        ...
        # Make this an async generator in the protocol
        yield ""

    async def complete_with_image(
        self,
        prompt: str,
        image_b64: str,
        *,
        system_prompt: str | None = None,
    ) -> str:
        """Send a multimodal prompt (text + image) and return the model's response.

        Args:
            prompt: The user prompt to send alongside the image
            image_b64: Base64-encoded image (PNG or JPEG)
            system_prompt: Optional system/instruction prompt

        Returns:
            The model's text response

        Raises:
            RuntimeError: If the LLM call fails or the model doesn't support images
            NotImplementedError: If the underlying provider doesn't support multimodal

        """
        ...

    async def complete_structured(
        self,
        prompt: str,
        schema: dict,
        *,
        system_prompt: str | None = None,
    ) -> dict:
        """Return a response constrained to ``schema`` (a JSON Schema dict).

        Args:
            prompt: The user prompt.
            schema: JSON Schema describing the required output object.
            system_prompt: Optional system/instruction prompt.

        Returns:
            A dict matching ``schema``.

        Raises:
            RuntimeError: If the LLM call fails.

        """
        ...

    async def get_model_info(self) -> dict[str, str]:
        """Get metadata about the active model.

        Returns:
            Dictionary with at minimum: provider, model_name

        """
        ...
