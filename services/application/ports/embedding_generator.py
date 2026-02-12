from typing import Protocol

from domain.value_objects.text_embedding import TextEmbedding


class EmbeddingGenerator(Protocol):
    """Port for generating embeddings from text content.

    This is a protocol (interface) that defines what the application layer
    expects from an embedding generator, without coupling to any specific
    implementation (sentence-transformers, OpenAI, etc.).

    Following the Ports & Adapters pattern from Clean Architecture.
    """

    async def generate_text_embedding(
        self,
        text: str,
        model_name: str | None = None,
    ) -> TextEmbedding:
        """Generate an embedding vector for the given text.

        Args:
            text: The text content to embed
            model_name: Optional override for the model name
                       (uses configured default if not provided)

        Returns:
            TextEmbedding: The generated embedding with metadata

        Raises:
            ValueError: If text is empty or invalid

        """
        ...

    async def get_model_info(self) -> dict[str, str | int]:
        """Get information about the current embedding model.

        Returns:
            Dictionary with model_name, dimensions, and provider info

        """
        ...
