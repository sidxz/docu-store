from typing import Protocol
from uuid import UUID

from domain.value_objects.text_embedding import TextEmbedding


class CompoundSearchResult:
    """Result from a compound vector similarity search."""

    def __init__(  # noqa: PLR0913
        self,
        page_id: UUID,
        artifact_id: UUID,
        score: float,
        page_index: int,
        smiles: str,
        canonical_smiles: str | None = None,
        extracted_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self.page_id = page_id
        self.artifact_id = artifact_id
        self.score = score
        self.page_index = page_index
        self.smiles = smiles
        self.canonical_smiles = canonical_smiles
        self.extracted_id = extracted_id
        self.metadata = metadata or {}


class CompoundVectorStore(Protocol):
    """Port for compound SMILES vector similarity operations.

    Stores one point per CompoundMention per page (not globally deduplicated).
    Each point carries the SMILES embedding plus compound metadata as payload.
    """

    async def ensure_compound_collection_exists(self) -> None:
        """Ensure the compound collection exists with proper schema.

        Idempotent — safe to call multiple times.
        """
        ...

    async def upsert_compound_embeddings(
        self,
        page_id: UUID,
        artifact_id: UUID,
        page_index: int,
        compounds: list[dict],
        embeddings: list[TextEmbedding],
    ) -> None:
        """Store or replace all compound embeddings for a page.

        Deletes any existing compound points for this page first, then inserts
        the new ones. Compounds and embeddings must be same length and aligned.

        Args:
            page_id: The page these compounds belong to
            artifact_id: The artifact this page belongs to
            page_index: Index of the page in the artifact
            compounds: List of compound metadata dicts with keys:
                smiles, canonical_smiles, extracted_id, confidence, is_smiles_valid
            embeddings: Corresponding TextEmbedding objects (one per compound)

        """
        ...

    async def delete_compound_embeddings_for_page(self, page_id: UUID) -> None:
        """Delete all compound embeddings for a given page.

        Idempotent — no error if page has no embeddings.
        """
        ...

    async def search_similar_compounds(
        self,
        query_embedding: TextEmbedding,
        limit: int = 10,
        artifact_id_filter: UUID | None = None,
        score_threshold: float | None = None,
    ) -> list[CompoundSearchResult]:
        """Find compounds structurally similar to the query SMILES embedding.

        Args:
            query_embedding: ChemBERTa embedding of the query SMILES
            limit: Maximum number of results to return
            artifact_id_filter: Optional filter to scope search to one artifact
            score_threshold: Optional minimum cosine similarity (0.0 to 1.0)

        Returns:
            List of CompoundSearchResult ordered by similarity (highest first)

        """
        ...

    async def get_compound_collection_info(self) -> dict:
        """Get stats for the compound collection."""
        ...
