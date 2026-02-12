from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TextEmbedding(BaseModel):
    """Represents a vector embedding of text content.

    This value object encapsulates the embedding vector and metadata
    about how it was generated, following domain-driven design principles.
    The actual vector is stored in the vector store, but this object
    provides domain context.
    """

    embedding_id: UUID
    """Unique identifier for this embedding."""

    vector: list[float]
    """The embedding vector (dense numerical representation of text)."""

    model_name: str
    """Name of the model used to generate this embedding."""

    dimensions: int
    """Dimensionality of the embedding vector."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    """Timestamp when the embedding was generated."""

    @field_validator("vector")
    @classmethod
    def validate_vector_not_empty(cls, v: list[float]) -> list[float]:
        """Ensure the vector is not empty."""
        if not v:
            msg = "Embedding vector cannot be empty"
            raise ValueError(msg)
        return v

    @field_validator("dimensions")
    @classmethod
    def validate_dimensions_match(cls, v: int, info) -> int:
        """Ensure dimensions match the actual vector length."""
        if "vector" in info.data:
            actual_dims = len(info.data["vector"])
            if v != actual_dims:
                msg = f"Declared dimensions ({v}) don't match vector length ({actual_dims})"
                raise ValueError(msg)
        return v

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        """Validate model name is not empty."""
        if not v or not v.strip():
            msg = "Model name cannot be empty"
            raise ValueError(msg)
        return v

    def __eq__(self, other: object) -> bool:
        """Compare embeddings by their ID."""
        if not isinstance(other, TextEmbedding):
            return NotImplemented
        return self.embedding_id == other.embedding_id

    def __hash__(self) -> int:
        """Hash based on embedding ID."""
        return hash(self.embedding_id)
