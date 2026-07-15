"""hiledit: application use case for human corrections to artifact metadata."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from application.mappers.artifact_mappers import ArtifactMapper
from application.mappers.page_mappers import PageMapper
from application.use_cases._guards import (
    handle_domain_errors,
    require_artifact_workspace,
    require_authenticated,
    require_editor,
    require_page_workspace,
)
from domain.services.tag_mention_aggregator import _normalize
from domain.value_objects.author_mention import AuthorMention
from domain.value_objects.compound_mention import CompoundMention
from domain.value_objects.presentation_date import PresentationDate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.title_mention import TitleMention

if TYPE_CHECKING:
    from uuid import UUID

    from application.dtos.artifact_dtos import ArtifactResponse
    from application.dtos.correction_dtos import (
        CorrectArtifactMetadataRequest,
        CorrectedTagInput,
        CorrectPageCompoundMentionsRequest,
    )
    from application.dtos.page_dtos import PageResponse
    from application.ports.auth import AuthContext
    from application.ports.external_event_publisher import ExternalEventPublisher
    from application.ports.repositories.artifact_repository import ArtifactRepository
    from application.ports.repositories.page_repository import PageRepository
    from application.ports.smiles_validator import SmilesValidator

logger = structlog.get_logger()


def _merge_tags(existing: list[TagMention], submitted: list[CorrectedTagInput]) -> list[TagMention]:
    """Keep the rich existing mention for tags the human retained; fresh mentions for additions."""
    now = datetime.now(UTC)
    by_key = {(m.entity_type, _normalize(m.tag)): m for m in existing}
    merged: list[TagMention] = []
    for s in submitted:
        kept = by_key.get((s.entity_type, _normalize(s.tag)))
        merged.append(
            kept
            if kept is not None
            else TagMention(
                tag=s.tag,
                entity_type=s.entity_type,
                tag_normalized=_normalize(s.tag),
                date_extracted=now,
            ),
        )
    return merged


def _merge_authors(existing: list[AuthorMention], submitted: list[str]) -> list[AuthorMention]:
    """Keep the rich existing mention for authors the human retained; fresh mentions for additions."""
    now = datetime.now(UTC)
    by_name = {m.name.casefold().strip(): m for m in existing}
    merged: list[AuthorMention] = []
    for name in submitted:
        kept = by_name.get(name.casefold().strip())
        merged.append(
            kept if kept is not None else AuthorMention(name=name.strip(), date_extracted=now),
        )
    return merged


class CorrectArtifactMetadataUseCase:
    """hiledit: apply human corrections to artifact metadata with provenance."""

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.external_event_publisher = external_event_publisher

    @handle_domain_errors
    async def execute(
        self,
        artifact_id: UUID,
        request: CorrectArtifactMetadataRequest,
        auth: AuthContext | None = None,
    ) -> Result[ArtifactResponse, AppError]:
        auth = require_authenticated(auth)
        require_editor(auth)

        provided = request.model_fields_set
        if not provided:
            return Failure(AppError("validation", "No fields to correct"))

        artifact = self.artifact_repository.get_by_id(artifact_id)
        require_artifact_workspace(auth, artifact)

        kwargs: dict = {}
        if "title" in provided:
            if request.title is not None and not request.title.strip():
                return Failure(AppError("validation", "Title cannot be blank"))
            kwargs["title_mention"] = (
                TitleMention(title=request.title.strip(), date_extracted=datetime.now(UTC))
                if request.title is not None
                else None
            )
        if "presentation_date" in provided:
            kwargs["presentation_date"] = (
                PresentationDate(
                    date=datetime(
                        request.presentation_date.year,
                        request.presentation_date.month,
                        request.presentation_date.day,
                        tzinfo=UTC,
                    ),
                    source="human",
                    date_extracted=datetime.now(UTC),
                )
                if request.presentation_date is not None
                else None
            )
        if "tags" in provided:
            kwargs["tag_mentions"] = _merge_tags(list(artifact.tag_mentions), request.tags or [])
        if "authors" in provided:
            kwargs["author_mentions"] = _merge_authors(
                list(artifact.author_mentions),
                request.authors or [],
            )

        corrected = artifact.correct_metadata(
            corrected_by_id=str(auth.user_id),
            corrected_by_name=auth.name,
            **kwargs,
        )
        self.artifact_repository.save(artifact)
        logger.info(
            "hiledit_artifact_metadata_corrected",
            artifact_id=str(artifact_id),
            fields=corrected,
            corrected_by=str(auth.user_id),
        )

        result = ArtifactMapper.to_artifact_response(artifact)
        if self.external_event_publisher:
            await self.external_event_publisher.notify_artifact_updated(
                result,
                sub_type="HumanCorrectionRecorded",
            )
        return Success(result)


class CorrectPageCompoundMentionsUseCase:
    """hiledit: replace a page's compound mentions with human-corrected ones."""

    def __init__(
        self,
        page_repository: PageRepository,
        smiles_validator: SmilesValidator,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.page_repository = page_repository
        self.smiles_validator = smiles_validator
        self.external_event_publisher = external_event_publisher

    @handle_domain_errors
    async def execute(
        self,
        page_id: UUID,
        request: CorrectPageCompoundMentionsRequest,
        auth: AuthContext | None = None,
    ) -> Result[PageResponse, AppError]:
        auth = require_authenticated(auth)
        require_editor(auth)

        page = self.page_repository.get_by_id(page_id)
        require_page_workspace(auth, page)

        # Round-trip an unchanged mention verbatim so its machine provenance
        # (confidence/model_name/pipeline_run_id/other_ids/date_extracted) survives
        # a correction that only touches a *sibling* mention. Identity keyed on the
        # human-editable fields the client can send.
        by_key = {
            (m.smiles, m.extracted_id, m.internal_id, m.cdd_id, m.chembl_id, m.pdb_id): m
            for m in page.compound_mentions
        }
        now = datetime.now(UTC)
        mentions: list[CompoundMention] = []
        for item in request.compound_mentions:
            existing = by_key.get(
                (
                    item.smiles,
                    item.extracted_id,
                    item.internal_id,
                    item.cdd_id,
                    item.chembl_id,
                    item.pdb_id,
                ),
            )
            if existing is not None:
                mentions.append(existing)
                continue
            canonical = self.smiles_validator.canonicalize(item.smiles)
            if canonical is None:
                return Failure(AppError("validation", f"Invalid SMILES: {item.smiles!r}"))
            mentions.append(
                CompoundMention(
                    smiles=item.smiles,
                    canonical_smiles=canonical,
                    is_smiles_valid=True,
                    extracted_id=item.extracted_id,
                    internal_id=item.internal_id,
                    cdd_id=item.cdd_id,
                    chembl_id=item.chembl_id,
                    pdb_id=item.pdb_id,
                    date_extracted=now,
                ),
            )

        page.correct_compound_mentions(
            mentions,
            corrected_by_id=str(auth.user_id),
            corrected_by_name=auth.name,
        )
        self.page_repository.save(page)
        logger.info(
            "hiledit_page_compound_mentions_corrected",
            page_id=str(page_id),
            count=len(mentions),
            corrected_by=str(auth.user_id),
        )

        result = PageMapper.to_page_response(page)
        if self.external_event_publisher:
            await self.external_event_publisher.notify_page_updated(
                result,
                sub_type="HumanCorrectionRecorded",
            )
        return Success(result)
