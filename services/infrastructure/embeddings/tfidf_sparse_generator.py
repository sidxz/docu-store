"""Hashing-based sparse embedding generator for hybrid search.

Uses scikit-learn HashingVectorizer to produce sparse vectors compatible
with Qdrant's SparseVector format. Provides exact-term recall for
scientific identifiers (compound codes, gene names, etc.).

Unlike TfidfVectorizer, HashingVectorizer requires no corpus fitting —
terms are mapped to indices via a deterministic hash function, so the
vocabulary never goes stale and no persistence is needed.
"""

from __future__ import annotations

import structlog
from sklearn.feature_extraction.text import HashingVectorizer

from application.ports.sparse_embedding_generator import SparseEmbedding, SparseEmbeddingGenerator

logger = structlog.get_logger()


class TfidfSparseGenerator(SparseEmbeddingGenerator):
    """Sparse embedding generator using scikit-learn HashingVectorizer.

    Stateless — no fitting, no persistence, no stale vocabulary.
    Same term always maps to the same index via deterministic hashing.
    """

    def __init__(
        self,
        n_features: int = 2**18,
        ngram_range: tuple[int, int] = (1, 2),
    ) -> None:
        self._vectorizer = HashingVectorizer(
            n_features=n_features,
            ngram_range=ngram_range,
            lowercase=True,
            token_pattern=r"(?u)\b\w[\w\-\.]+\b",  # keeps hyphens/dots (SACC-111, IC50)
            alternate_sign=False,  # all values non-negative
            norm="l2",  # unit-normalize for cosine-like scoring
        )
        logger.info(
            "sparse_generator_initialized",
            type="hashing",
            n_features=n_features,
            ngram_range=ngram_range,
        )

    def fit(self, corpus: list[str]) -> None:
        """No-op — HashingVectorizer does not require fitting."""

    def generate_sparse_embedding(self, text: str) -> SparseEmbedding:
        """Generate a sparse hashing vector for a single text."""
        matrix = self._vectorizer.transform([text])
        csr = matrix.tocsr()[0]

        return SparseEmbedding(
            indices=csr.indices.tolist(),
            values=csr.data.tolist(),
        )

    def generate_batch_sparse_embeddings(self, texts: list[str]) -> list[SparseEmbedding]:
        """Generate sparse hashing vectors for a batch of texts."""
        matrix = self._vectorizer.transform(texts)

        results = []
        for i in range(matrix.shape[0]):
            row = matrix.getrow(i).tocsr()
            results.append(
                SparseEmbedding(
                    indices=row.indices.tolist(),
                    values=row.data.tolist(),
                ),
            )
        return results
