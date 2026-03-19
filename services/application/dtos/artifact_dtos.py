from uuid import UUID

from pydantic import BaseModel, Field

from application.dtos.page_dtos import PageResponse
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.author_mention import AuthorMention
from domain.value_objects.mime_type import MimeType
from domain.value_objects.presentation_date import PresentationDate
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.title_mention import TitleMention


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
    workspace_id: UUID | None = Field(None, description="Workspace this artifact belongs to")
    owner_id: UUID | None = Field(None, description="User who created this artifact")
    pages: list[UUID] | list[PageResponse] | None = Field(
        default_factory=list,
        description="List of page IDs associated with the artifact",
    )
    title_mention: TitleMention | None = Field(
        None,
        description="Title mention extracted from the artifact",
    )
    tag_mentions: list[TagMention] = Field(
        default_factory=list,
        description="Structured tag mentions aggregated from all pages",
    )
    author_mentions: list[AuthorMention] = Field(
        default_factory=list,
        description="Author mentions extracted from the document",
    )
    presentation_date: PresentationDate | None = Field(
        None,
        description="Presentation or publication date extracted from the document",
    )
    summary_candidate: SummaryCandidate | None = Field(
        None,
        description="Summary candidate extracted from the artifact",
    )
