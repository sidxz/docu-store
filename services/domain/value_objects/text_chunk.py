from pydantic import BaseModel, field_validator


class TextChunk(BaseModel):
    """Represents a chunk of text extracted from a page for embedding.

    When page text is too long for an embedding model's context window,
    the text is split into overlapping chunks. Each chunk produces its
    own embedding vector in the vector store.

    This value object is model-agnostic — chunking is done by character
    count, not tokens, so switching embedding models only requires
    changing configuration, not code.
    """

    chunk_index: int
    """Position of this chunk within the page (0-based)."""

    text: str
    """The chunk text content."""

    start_char: int
    """Character offset where this chunk starts in the original page text."""

    end_char: int
    """Character offset where this chunk ends in the original page text."""

    total_chunks: int
    """Total number of chunks the page was split into."""

    @field_validator("text")
    @classmethod
    def validate_text_not_empty(cls, v: str) -> str:
        """Ensure the chunk text is not empty."""
        if not v or not v.strip():
            msg = "Chunk text cannot be empty"
            raise ValueError(msg)
        return v

    @field_validator("chunk_index")
    @classmethod
    def validate_chunk_index(cls, v: int) -> int:
        """Ensure chunk index is non-negative."""
        if v < 0:
            msg = "Chunk index must be non-negative"
            raise ValueError(msg)
        return v

    @field_validator("total_chunks")
    @classmethod
    def validate_total_chunks(cls, v: int) -> int:
        """Ensure total chunks is positive."""
        if v < 1:
            msg = "Total chunks must be at least 1"
            raise ValueError(msg)
        return v
