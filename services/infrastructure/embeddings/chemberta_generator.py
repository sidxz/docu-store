from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

import structlog

from application.ports.embedding_generator import EmbeddingGenerator
from domain.value_objects.text_embedding import TextEmbedding

if TYPE_CHECKING:
    import torch
    from transformers import AutoModel, AutoTokenizer

logger = structlog.get_logger()

_CHEMBERTA_DIMENSIONS = 384


class ChemBertaEmbeddingGenerator(EmbeddingGenerator):
    """Adapter for generating SMILES embeddings using ChemBERTa.

    Implements the EmbeddingGenerator port using HuggingFace transformers.
    Applies mean pooling over token embeddings (attention-mask weighted),
    which is the standard approach for ChemBERTa-style models.

    Default model: DeepChem/ChemBERTa-77M-MTR (384-dim, trained on SMILES)
    """

    def __init__(
        self,
        model_name: str = "DeepChem/ChemBERTa-77M-MTR",
        device: Literal["cpu", "cuda", "mps"] = "cpu",
    ) -> None:
        self.model_name = model_name
        self.device = device

        logger.info(
            "initializing_chemberta_generator",
            model_name=model_name,
            device=device,
        )

        # Lazy-loaded on first use — heavy imports kept out of module scope
        self._tokenizer: AutoTokenizer | None = None
        self._model: AutoModel | None = None
        self._torch: torch | None = None

    def _ensure_model_loaded(self) -> None:
        """Lazy-load tokenizer and model on first use."""
        if self._model is not None:
            return

        import torch  # noqa: PLC0415
        from transformers import AutoModel, AutoTokenizer  # noqa: PLC0415

        logger.info("loading_chemberta_model", model_name=self.model_name)

        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModel.from_pretrained(self.model_name)
        self._model.to(self.device)
        self._model.eval()

        logger.info(
            "chemberta_model_loaded",
            model_name=self.model_name,
            device=self.device,
        )

    def _mean_pool(
        self,
        token_embeddings: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> torch.Tensor:
        """Mean-pool token embeddings weighted by attention mask."""
        mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        sum_embeddings = self._torch.sum(token_embeddings * mask_expanded, dim=1)
        sum_mask = self._torch.clamp(mask_expanded.sum(1), min=1e-9)
        return sum_embeddings / sum_mask

    def _encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Tokenize and encode a batch of SMILES strings."""
        self._ensure_model_loaded()

        inputs = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with self._torch.no_grad():
            outputs = self._model(**inputs)

        pooled = self._mean_pool(outputs.last_hidden_state, inputs["attention_mask"])
        return pooled.cpu().numpy().tolist()

    async def generate_text_embedding(
        self,
        text: str,
        model_name: str | None = None,  # noqa: ARG002
    ) -> TextEmbedding:
        """Generate a ChemBERTa embedding for a single SMILES string."""
        if not text or not text.strip():
            msg = "SMILES cannot be empty"
            raise ValueError(msg)

        vectors = self._encode_batch([text])
        vector = vectors[0]

        return TextEmbedding(
            embedding_id=uuid4(),
            vector=vector,
            model_name=self.model_name,
            dimensions=len(vector),
            generated_at=datetime.now(UTC),
        )

    async def generate_batch_embeddings(
        self,
        texts: list[str],
        model_name: str | None = None,  # noqa: ARG002
    ) -> list[TextEmbedding]:
        """Generate ChemBERTa embeddings for a batch of SMILES strings."""
        if not texts:
            msg = "Texts list cannot be empty"
            raise ValueError(msg)

        for i, text in enumerate(texts):
            if not text or not text.strip():
                msg = f"SMILES at index {i} cannot be empty"
                raise ValueError(msg)

        logger.debug("generating_chemberta_batch", count=len(texts))

        vectors = self._encode_batch(texts)
        now = datetime.now(UTC)

        embeddings = [
            TextEmbedding(
                embedding_id=uuid4(),
                vector=vector,
                model_name=self.model_name,
                dimensions=len(vector),
                generated_at=now,
            )
            for vector in vectors
        ]

        logger.debug("chemberta_batch_generated", count=len(embeddings))
        return embeddings

    async def get_model_info(self) -> dict[str, str | int]:
        """Get information about the ChemBERTa model."""
        return {
            "model_name": self.model_name,
            "dimensions": _CHEMBERTA_DIMENSIONS,
            "provider": "transformers/chemberta",
            "device": self.device,
        }
