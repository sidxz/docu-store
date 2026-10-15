from __future__ import annotations

import threading
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
        model_name: str = "ibm-granite/granite-embedding-english-r2",
        device: Literal["cpu", "cuda", "mps"] = "cpu",
        query_prefix: str = "",
        document_prefix: str = "",
    ) -> None:
        """Initialize the sentence-transformers generator.

        Args:
            model_name: HuggingFace model name or path
            device: Device to run the model on (cpu, cuda, or mps for Apple Silicon)
            query_prefix: Prefix prepended to query text, for models trained with one
            document_prefix: Prefix prepended to document text, for models trained with one

        """
        self.model_name = model_name
        self.device = self._resolve_device(device)
        self.query_prefix = query_prefix
        self.document_prefix = document_prefix

        logger.info(
            "initializing_sentence_transformer",
            model_name=model_name,
            device=self.device,
        )

        # Lazy loading - will load on first use
        self._model: SentenceTransformer | None = None
        self._dimensions: int | None = None
        self._lock = threading.Lock()

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
        """Lazy load the model on first use (thread-safe double-check locking)."""
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            from sentence_transformers import (
                SentenceTransformer,
            )  # heavy import — deferred until first use

            logger.info("loading_sentence_transformer_model", model_name=self.model_name)
            # sentence-transformers keeps a checkpoint's saved dtype; bf16/fp16
            # weights run ~12x slower on CPU than fp32. No trust_remote_code:
            # only architectures transformers ships natively are loaded.
            model_kwargs = None
            if self.device == "cpu":
                import torch

                model_kwargs = {"torch_dtype": torch.float32}
            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
                model_kwargs=model_kwargs,
            )
            self._dimensions = self._model.get_embedding_dimension()
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

        # Asymmetric retrieval models expect a query-side prefix
        prefixed_text = self.query_prefix + text if self.query_prefix else text
        vector = self._model.encode(prefixed_text, convert_to_tensor=False).tolist()

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

        # Asymmetric retrieval models expect a document-side prefix
        if self.document_prefix:
            texts = [self.document_prefix + t for t in texts]

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
