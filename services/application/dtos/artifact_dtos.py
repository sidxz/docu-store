from uuid import UUID

from pydantic import BaseModel, Field

from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.title_mention import TitleMention


class CreateArtifactRequest(BaseModel):
    """Request DTO for creating a new artifact."""

    source_uri: str = Field(..., description="URI pointing to the source of the artifact")
    source_filename: str = Field(..., description="Original filename of the artifact")
    artifact_type: ArtifactType = Field(..., description="Classification type of the artifact")
    mime_type: MimeType = Field(..., description="MIME type of the artifact")
    storage_location: str = Field(..., description="Location where the artifact is stored")


class ArtifactResponse(BaseModel):
    """Response DTO representing an artifact."""

    artifact_id: UUID = Field(..., description="Unique identifier of the artifact")
    source_uri: str = Field(..., description="URI pointing to the source of the artifact")
    source_filename: str = Field(..., description="Original filename of the artifact")
    artifact_type: ArtifactType = Field(..., description="Classification type of the artifact")
    mime_type: MimeType = Field(..., description="MIME type of the artifact")
    storage_location: str = Field(..., description="Location where the artifact is stored")
    pages: tuple[UUID, ...] = Field(
        default_factory=tuple,
        description="List of page UUIDs associated with the artifact",
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
