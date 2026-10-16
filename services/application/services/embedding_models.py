"""API embedding models a workspace may choose — the single place their ids live.

A workspace stores one *canonical* id (the key of ``EMBEDDING_MODELS``); that id
is also the ``model_name`` written next to every vector, whichever key served it.
Each model can be reached through the members' own LLM keys: ``providers`` maps
a user-facing provider id (the BYO-LLM registry's) to that provider's name for
the same model, in preference order. OpenRouter proxies the same upstream model,
so vectors from either route land in the same space.

Every model is asked for ``EMBEDDING_DIMENSIONS`` (768) dimensions, so the one
Qdrant collection serves all of them, separated by workspace.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from application.services.llm_providers import OPENROUTER_BASE_URL

LOCAL_EMBEDDING_MODEL = "local"  # the server's own model (EMBEDDING_MODEL_NAME)


@dataclass(frozen=True)
class EmbeddingModelPreset:
    label: str
    providers: dict[str, str]  # user-facing provider id -> that provider's model id
    # Gemini Embedding 2 takes its task as text instead of a task_type field.
    query_prefix: str = ""
    document_prefix: str = ""


EMBEDDING_MODELS: dict[str, EmbeddingModelPreset] = {
    "openai/text-embedding-3-small": EmbeddingModelPreset(
        "OpenAI text-embedding-3-small",
        {"openai": "text-embedding-3-small", "openrouter": "openai/text-embedding-3-small"},
    ),
    "openai/text-embedding-3-large": EmbeddingModelPreset(
        "OpenAI text-embedding-3-large",
        {"openai": "text-embedding-3-large", "openrouter": "openai/text-embedding-3-large"},
    ),
    "google/gemini-embedding-2": EmbeddingModelPreset(
        "Google Gemini Embedding 2",
        {"gemini": "gemini-embedding-2", "openrouter": "google/gemini-embedding-2"},
        query_prefix="task: search result | query: ",
        document_prefix="title: none | text: ",
    ),
}

# The SDK each user-facing provider is called through.
_SDK = {"openai": "openai", "openrouter": "openai", "gemini": "gemini"}
_PROVIDER_LABELS = {"openai": "OpenAI", "openrouter": "OpenRouter", "gemini": "Gemini"}


@dataclass(frozen=True)
class EmbeddingSpec:
    """Everything an API embedding call needs. Frozen: it is the client cache key."""

    model: str  # recorded as the vector's model_name
    sdk: str  # openai | gemini
    provider_model: str
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None
    query_prefix: str = ""
    document_prefix: str = ""
    # Set when no key can serve ``model``: the generator raises this, fail closed.
    missing_key_message: str | None = None


def spec_for_provider(model: str, provider: str, api_key: str | None) -> EmbeddingSpec:
    """``model`` (a canonical id) served through ``provider``'s key."""
    preset = EMBEDDING_MODELS[model]
    return EmbeddingSpec(
        model=model,
        sdk=_SDK[provider],
        provider_model=preset.providers[provider],
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL if provider == "openrouter" else None,
        query_prefix=preset.query_prefix,
        document_prefix=preset.document_prefix,
    )


def missing_key_spec(model: str) -> EmbeddingSpec:
    preset = EMBEDDING_MODELS.get(model)
    if preset is None:
        message = f"This workspace's embedding model '{model}' is no longer supported."
        return EmbeddingSpec(
            model=model, sdk="openai", provider_model=model, missing_key_message=message
        )
    names = " or ".join(_PROVIDER_LABELS[p] for p in preset.providers)
    message = (
        f"This workspace searches with {preset.label}, which needs a key from {names}. "
        "A workspace admin can connect one under Settings → AI Provider."
    )
    first = next(iter(preset.providers))
    return EmbeddingSpec(
        model=model,
        sdk=_SDK[first],
        provider_model=preset.providers[first],
        missing_key_message=message,
    )
