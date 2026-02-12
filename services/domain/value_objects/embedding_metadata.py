from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EmbeddingMetadata(BaseModel):
    """Metadata about an embedding stored in the domain aggregate.

    This is lightweight metadata that lives in the domain,
    while the actual vectors live in the vector store.
    This separation follows the DDD principle of keeping
    aggregates focused on business logic, not storage concerns.
    """

    embedding_id: UUID
    """Reference to the embedding stored in the vector store."""

    model_name: str
    """Name of the model used to generate the embedding."""

    dimensions: int
    """Dimensionality of the embedding vector."""

    generated_at: datetime
    """When this embedding was generated."""

    embedding_type: str = Field(default="text")
    """Type of embedding (text, chemical, etc.). Allows for future multi-modal embeddings."""

    def __eq__(self, other: object) -> bool:
        """Compare metadata by embedding ID."""
        if not isinstance(other, EmbeddingMetadata):
            return NotImplemented
        return self.embedding_id == other.embedding_id

    def __hash__(self) -> int:
        """Hash based on embedding ID."""
        return hash(self.embedding_id)
