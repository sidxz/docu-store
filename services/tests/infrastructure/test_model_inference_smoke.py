"""Every configured ML model must load AND run one inference.

Loading alone proves nothing: transformers 5.17 removed a method that the
previous embedding model's remote code still called, so the model loaded, the
status page showed it as healthy, and the first encode call in production
raised. Nothing else in the suite touches a real model, so this is the one
check that fails when a dependency bump breaks inference.

First run downloads the models (about 1 GB, cached under
~/.cache/huggingface afterwards).
"""

import pytest

from application.ports.reranker import RerankDocument
from infrastructure.config import settings

pytestmark = pytest.mark.integration


# Both supported local models must keep working on every dependency bump: a
# deployment may pin either (nomic keeps existing vectors valid, granite is the
# default). The configured model is added in case it is a third one.
TEXT_MODELS = sorted(
    {"ibm-granite/granite-embedding-english-r2", "nomic-ai/nomic-embed-text-v1.5"}
    | ({settings.embedding_model_name} if settings.embedding_model_provider == "sentence-transformers" else set())
)


@pytest.mark.parametrize("model_name", TEXT_MODELS)
async def test_text_embedding_model_encodes(model_name: str) -> None:
    from infrastructure.embeddings.sentence_transformer_generator import (
        SentenceTransformerGenerator,
    )

    generator = SentenceTransformerGenerator(
        model_name=model_name,
        device=settings.embedding_device,
    )
    embedding = await generator.generate_text_embedding("inference smoke")
    assert embedding.dimensions > 0
    assert len(embedding.vector) == embedding.dimensions


async def test_smiles_embedding_model_encodes() -> None:
    from infrastructure.embeddings.chemberta_generator import ChemBertaEmbeddingGenerator

    generator = ChemBertaEmbeddingGenerator(
        model_name=settings.smiles_embedding_model_name,
        device=settings.smiles_embedding_device,
    )
    embedding = await generator.generate_text_embedding("CC(=O)Oc1ccccc1C(=O)O")
    assert len(embedding.vector) == embedding.dimensions > 0


def test_reranker_model_scores() -> None:
    from infrastructure.rerankers.cross_encoder_reranker import CrossEncoderReranker

    reranker = CrossEncoderReranker(
        model_name=settings.reranker_model_name,
        device=settings.reranker_device,
    )
    results = reranker.rerank(
        "aspirin dosage",
        [
            RerankDocument(id="hit", text="Aspirin is dosed at 75 to 325 mg daily."),
            RerankDocument(id="miss", text="Quarterly revenue grew eight percent."),
        ],
    )
    scores = {r.id: r.score for r in results}
    # The adapter abstains (score None) below its floor, so the off-topic
    # document may legitimately come back unscored.
    assert scores["hit"] is not None
    assert scores["hit"] > 0.5
    assert scores["miss"] is None or scores["miss"] < scores["hit"]
