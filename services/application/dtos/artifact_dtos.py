from uuid import UUID

from pydantic import BaseModel, Field

from application.dtos.page_dtos import PageResponse
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.title_mention import TitleMention
from domain.value_objects.workflow_status import WorkflowStatus


class CreateArtifactRequest(BaseModel):
    """Request DTO for creating a new artifact."""

    artifact_id: UUID | None = Field(
        None,
        description="Optional artifact ID to use instead of generating a new one",
    )
    source_uri: str | None = Field(None, description="URI pointing to the source of the artifact")
    source_filename: str | None = Field(None, description="Original filename of the artifact")
    artifact_type: ArtifactType = Field(..., description="Classification type of the artifact")
    mime_type: MimeType = Field(..., description="MIME type of the artifact")
    storage_location: str = Field(..., description="Location where the artifact is stored")


class ArtifactResponse(BaseModel):
    """Response DTO representing an artifact."""

    artifact_id: UUID = Field(..., description="Unique identifier of the artifact")
    source_uri: str | None = Field(None, description="URI pointing to the source of the artifact")
    source_filename: str | None = Field(None, description="Original filename of the artifact")
    artifact_type: ArtifactType = Field(..., description="Classification type of the artifact")
    mime_type: MimeType = Field(..., description="MIME type of the artifact")
    storage_location: str = Field(..., description="Location where the artifact is stored")
    pages: list[UUID] | list[PageResponse] | None = Field(
        default_factory=list,
        description="List of page IDs associated with the artifact",
    )
    title_mention: TitleMention | None = Field(
        None,
        description="Title mention extracted from the artifact",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="List of tags associated with the artifact",
    )
    summary_candidate: SummaryCandidate | None = Field(
        None,
        description="Summary candidate extracted from the artifact",
    )
    workflow_statuses: dict[str, WorkflowStatus] = Field(
        default_factory=dict,
        description="Workflow statuses keyed by workflow name",
    )
