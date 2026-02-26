from typing import Protocol

from domain.value_objects.text_chunk import TextChunk


class TextChunker(Protocol):
    """Port for splitting text into chunks for embedding.

    This is a protocol (interface) that defines how page text should be
    split into smaller, overlapping chunks before generating embeddings.

    The chunking strategy is abstracted behind this port so that:
    - Chunk sizes can be adjusted per embedding model via configuration
    - The chunking library (LangChain, custom, etc.) can be swapped
    - The application layer remains agnostic to chunking implementation

    Following the Ports & Adapters pattern from Clean Architecture.
    """

    def chunk_text(self, text: str) -> list[TextChunk]:
        """Split text into overlapping chunks suitable for embedding.

        If the text is short enough to fit in a single chunk, returns
        a list with one chunk containing the full text.

        Args:
            text: The full text content to split

        Returns:
            List of TextChunk value objects, ordered by chunk_index

        """
        ...
