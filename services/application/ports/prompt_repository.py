from __future__ import annotations

from typing import Protocol


class PromptRepositoryPort(Protocol):
    """Port for rendering versioned prompt templates.

    Concrete adapters live in infrastructure/llm/prompt_repositories/ and
    implement Langfuse (primary) and YAML file fallback.

    Following the Ports & Adapters pattern from Clean Architecture.
    """

    async def render_prompt(
        self,
        name: str,
        version: str | None = None,
        **variables: str,
    ) -> str:
        """Fetch and render a prompt template by name.

        Args:
            name: Prompt identifier (e.g. "page_summarization_hybrid")
            version: Specific version to fetch. Fetches the latest if None.
            **variables: Values to substitute into the template.

        Returns:
            The fully rendered prompt string.

        Raises:
            KeyError: If the prompt name is not found
            RuntimeError: If the prompt backend is unreachable

        """
        ...
