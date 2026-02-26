from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

import structlog

from application.ports.embedding_generator import EmbeddingGenerator
from domain.value_objects.text_embedding import TextEmbedding

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = structlog.get_logger()


class SentenceTransformerGenerator(EmbeddingGenerator):
    """Adapter for generating embeddings using sentence-transformers library.

    This is an implementation of the EmbeddingGenerator port,
    using the sentence-transformers library for local embedding generation.

    Supports various pre-trained models like:
    - sentence-transformers/all-MiniLM-L6-v2 (384 dimensions, fast)
    - intfloat/e5-large-v2 (1024 dimensions, better quality)
    - etc.
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        device: Literal["cpu", "cuda", "mps"] = "cpu",
    ):
        """Initialize the sentence-transformers generator.

        Args:
            model_name: HuggingFace model name or path
            device: Device to run the model on (cpu, cuda, or mps for Apple Silicon)

        """
        self.model_name = model_name
        self.device = self._resolve_device(device)

        logger.info(
            "initializing_sentence_transformer",
            model_name=model_name,
            device=self.device,
        )

        # Lazy loading - will load on first use
        self._model: SentenceTransformer | None = None
        self._dimensions: int | None = None

    def _resolve_device(self, device: str) -> str:
        """Resolve and validate the device."""
        import torch  # heavy import — deferred until first instantiation

        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("cuda_not_available_falling_back_to_cpu")
            return "cpu"
        if device == "mps" and not torch.backends.mps.is_available():
            logger.warning("mps_not_available_falling_back_to_cpu")
            return "cpu"
        return device

    def _ensure_model_loaded(self) -> None:
        """Lazy load the model on first use."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # heavy import — deferred until first use

            logger.info("loading_sentence_transformer_model", model_name=self.model_name)
            self._model = SentenceTransformer(self.model_name, device=self.device)
            self._dimensions = self._model.get_sentence_embedding_dimension()
            logger.info(
                "model_loaded",
                model_name=self.model_name,
                dimensions=self._dimensions,
            )

    async def generate_text_embedding(
        self,
        text: str,
        model_name: str | None = None,
    ) -> TextEmbedding:
        """Generate an embedding vector for the given text.

        Args:
            text: The text content to embed
            model_name: Ignored - uses the configured model

        Returns:
            TextEmbedding with the generated vector and metadata

        Raises:
            ValueError: If text is empty or invalid

        """
        if not text or not text.strip():
            msg = "Text cannot be empty"
            raise ValueError(msg)

        self._ensure_model_loaded()

        logger.debug("generating_embedding", text_length=len(text))

        # Generate embedding
        # encode() returns numpy array, convert to list
        vector = self._model.encode(text, convert_to_tensor=False).tolist()

        embedding = TextEmbedding(
            embedding_id=uuid4(),
            vector=vector,
            model_name=self.model_name,
            dimensions=len(vector),
            generated_at=datetime.now(UTC),
        )

        logger.debug(
            "embedding_generated",
            embedding_id=str(embedding.embedding_id),
            dimensions=embedding.dimensions,
        )

        return embedding

    async def generate_batch_embeddings(
        self,
        texts: list[str],
        model_name: str | None = None,
    ) -> list[TextEmbedding]:
        """Generate embeddings for multiple texts in a single batch.

        Uses sentence-transformers batch encoding for efficiency.

        Args:
            texts: List of text content to embed
            model_name: Ignored - uses the configured model

        Returns:
            List of TextEmbedding objects, one per input text

        Raises:
            ValueError: If texts is empty or any text is empty

        """
        if not texts:
            msg = "Texts list cannot be empty"
            raise ValueError(msg)

        for i, text in enumerate(texts):
            if not text or not text.strip():
                msg = f"Text at index {i} cannot be empty"
                raise ValueError(msg)

        self._ensure_model_loaded()

        logger.debug("generating_batch_embeddings", count=len(texts))

        # Batch encode all texts at once — much faster than encoding one by one
        vectors = self._model.encode(texts, convert_to_tensor=False).tolist()

        embeddings = [
            TextEmbedding(
                embedding_id=uuid4(),
                vector=vector,
                model_name=self.model_name,
                dimensions=len(vector),
                generated_at=datetime.now(UTC),
            )
            for vector in vectors
        ]

        logger.debug(
            "batch_embeddings_generated",
            count=len(embeddings),
            dimensions=embeddings[0].dimensions if embeddings else 0,
        )

        return embeddings

    async def get_model_info(self) -> dict[str, str | int]:
        """Get information about the current embedding model."""
        self._ensure_model_loaded()

        return {
            "model_name": self.model_name,
            "dimensions": self._dimensions,
            "provider": "sentence-transformers",
            "device": self.device,
        }
