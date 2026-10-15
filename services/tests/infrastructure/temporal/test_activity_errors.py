"""LLM activities never report a failed use case as a completed activity."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from returns.result import Failure, Success
from temporalio.exceptions import ApplicationError

from application.dtos.errors import AppError
from domain.exceptions import LLMAuthError, LLMNotConfiguredError, LLMRateLimitedError
from infrastructure.temporal.activities.artifact_summarization_activities import (
    create_summarize_artifact_activity,
)
from infrastructure.temporal.activities.document_metadata_activities import (
    create_extract_document_metadata_activity,
)
from infrastructure.temporal.activities.ner_activities import (
    create_aggregate_artifact_tags_activity,
    create_extract_page_entities_activity,
)
from infrastructure.temporal.activities.summarization_activities import (
    create_summarize_page_activity,
)


class _UseCase:
    def __init__(self, outcome) -> None:  # noqa: ANN001
        self._outcome = outcome

    async def execute(self, **kwargs):  # noqa: ANN003, ANN202
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome


ONE_ID = [str(uuid4())]
TWO_IDS = [str(uuid4()), str(uuid4())]
FACTORIES = [
    (create_summarize_page_activity, ONE_ID),
    (create_summarize_artifact_activity, ONE_ID),
    (create_extract_page_entities_activity, ONE_ID),
    (create_aggregate_artifact_tags_activity, ONE_ID),
    (create_extract_document_metadata_activity, TWO_IDS),
]


@pytest.mark.parametrize(("factory", "args"), FACTORIES)
@pytest.mark.parametrize("exc", [LLMAuthError("402 payment required"), LLMNotConfiguredError("no key")])
async def test_non_retryable_llm_errors(factory, args, exc) -> None:
    with pytest.raises(ApplicationError) as info:
        await factory(_UseCase(exc))(*args)
    assert info.value.non_retryable is True
    assert info.value.type == type(exc).__name__


@pytest.mark.parametrize(("factory", "args"), FACTORIES)
async def test_rate_limit_is_retryable(factory, args) -> None:
    with pytest.raises(ApplicationError) as info:
        await factory(_UseCase(LLMRateLimitedError("429")))(*args)
    assert info.value.non_retryable is False


@pytest.mark.parametrize(("factory", "args"), FACTORIES)
@pytest.mark.parametrize(
    ("category", "non_retryable"),
    [("not_found", True), ("validation", True), ("not_ready", True),
     ("concurrency", False), ("internal_error", False)],
)
async def test_failures_raise_instead_of_returning(factory, args, category, non_retryable) -> None:
    with pytest.raises(ApplicationError) as info:
        await factory(_UseCase(Failure(AppError(category, "msg"))))(*args)
    assert info.value.non_retryable is non_retryable
    assert info.value.type == category


@pytest.mark.parametrize(("factory", "args"), FACTORIES)
async def test_unknown_exception_still_propagates_for_retry(factory, args) -> None:
    with pytest.raises(RuntimeError):
        await factory(_UseCase(RuntimeError("ollama down")))(*args)


async def test_success_payloads_unchanged() -> None:
    resp = SimpleNamespace(summary_candidate=SimpleNamespace(summary="abc"))
    out = await create_summarize_page_activity(_UseCase(Success(resp)))(ONE_ID[0])
    assert out == {"status": "success", "page_id": ONE_ID[0], "summary_len": 3}
    out = await create_summarize_artifact_activity(_UseCase(Success(resp)))(ONE_ID[0])
    assert out == {"status": "success", "artifact_id": ONE_ID[0], "summary_len": 3}
    payload = {"status": "success", "page_id": ONE_ID[0], "entity_count": 2}
    assert await create_extract_page_entities_activity(_UseCase(Success(payload)))(ONE_ID[0]) == payload
    payload = {"status": "success", "artifact_id": ONE_ID[0], "tag_count": 1}
    assert await create_aggregate_artifact_tags_activity(_UseCase(Success(payload)))(ONE_ID[0]) == payload
    payload = {"status": "success", "artifact_id": TWO_IDS[0], "author_count": 1}
    assert await create_extract_document_metadata_activity(_UseCase(Success(payload)))(*TWO_IDS) == payload


# ── Embedding activities: a provider failure or an internal error must fail the
# workflow; "nothing to embed" (blank page, deleted artifact) stays completed.

from infrastructure.temporal.activities.batch_reembed_activities import (  # noqa: E402
    create_batch_reembed_artifact_pages_activity,
)
from infrastructure.temporal.activities.batch_reembed_summaries_activities import (  # noqa: E402
    create_batch_reembed_summaries_activity,
)
from infrastructure.temporal.activities.embedding_activities import (  # noqa: E402
    create_generate_page_embedding_activity,
)
from infrastructure.temporal.activities.summary_embedding_activities import (  # noqa: E402
    create_embed_artifact_summary_activity,
    create_embed_page_summary_activity,
)

EMBEDDING_FACTORIES = [
    create_generate_page_embedding_activity,
    create_embed_page_summary_activity,
    create_embed_artifact_summary_activity,
]


@pytest.mark.parametrize(
    "factory",
    [*EMBEDDING_FACTORIES, create_batch_reembed_artifact_pages_activity,
     create_batch_reembed_summaries_activity],
)
async def test_embedding_provider_errors_fail_the_workflow(factory) -> None:
    with pytest.raises(ApplicationError) as info:
        await factory(_UseCase(LLMNotConfiguredError("no key")))(ONE_ID[0])
    assert info.value.non_retryable is True
    assert info.value.type == "LLMNotConfiguredError"


@pytest.mark.parametrize("factory", EMBEDDING_FACTORIES)
@pytest.mark.parametrize("category", ["internal_error", "concurrency"])
async def test_embedding_failures_raise_for_retry(factory, category) -> None:
    with pytest.raises(ApplicationError) as info:
        await factory(_UseCase(Failure(AppError(category, "msg"))))(ONE_ID[0])
    assert info.value.non_retryable is False


@pytest.mark.parametrize("factory", EMBEDDING_FACTORIES)
@pytest.mark.parametrize("category", ["validation", "not_found"])
async def test_nothing_to_embed_stays_completed(factory, category) -> None:
    out = await factory(_UseCase(Failure(AppError(category, "blank page"))))(ONE_ID[0])
    assert out["status"] == "failed"
    assert out["error_code"] == category
