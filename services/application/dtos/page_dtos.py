from uuid import UUID

from pydantic import BaseModel

from domain.value_objects.compound_mention import CompoundMention
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.text_mention import TextMention


class CreatePageRequest(BaseModel):
    name: str
    artifact_id: UUID
    index: int = 0
    page_id: UUID | None = None
    # NOTE: workspace_id/owner_id are deliberately NOT here. Page identity is never
    # taken from the (potentially HTTP-bound) request body — it comes from auth, or
    # from explicit args on CreatePageUseCase.execute() that only trusted internal
    # callers (the parse activity) pass. See CreatePageUseCase for the rationale.


class AddCompoundMentionsRequest(BaseModel):
    page_id: UUID
    compound_mentions: list[CompoundMention]


class PageResponse(BaseModel):
    page_id: UUID
    artifact_id: UUID
    name: str
    index: int
    compound_mentions: list[CompoundMention]
    tag_mentions: list[TagMention] = []
    text_mention: TextMention | None = None
    summary_candidate: SummaryCandidate | None = None
    workspace_id: UUID | None = None
    owner_id: UUID | None = None
