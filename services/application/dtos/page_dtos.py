from uuid import UUID

from pydantic import BaseModel, Field

from domain.value_objects.compound_mention import CompoundMention
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.text_mention import TextMention
from domain.value_objects.workflow_status import WorkflowStatus


class CreatePageRequest(BaseModel):
    name: str
    artifact_id: UUID
    index: int = 0


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
    workflow_statuses: dict[str, WorkflowStatus] = Field(
        default_factory=dict,
        description="Workflow statuses keyed by workflow name",
    )
