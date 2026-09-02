from uuid import UUID

from pydantic import BaseModel, Field

from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.source_class import SourceClass


class UploadBlobRequest(BaseModel):
    source_uri: str | None = Field(None, description="URI pointing to the source of the artifact")
    artifact_type: ArtifactType = Field(..., description="Classification type of the artifact")
    filename: str | None = Field(None, description="Original filename of the artifact")
    mime_type: str | None
    visibility: str = Field("workspace", description="Initial visibility: 'workspace' or 'private'")
    source_class: SourceClass = Field(
        SourceClass.INTERNAL,
        description="Where the document came from, and so what may be done with it",
    )
    licence: str | None = Field(None, description="Licence the document was ingested under")


class UploadBlobResponse(BaseModel):
    artifact_id: UUID = Field(..., description="Unique identifier of the artifact")
    storage_key: str = Field(..., description="Storage key of the artifact")
    sha256: str = Field(..., description="SHA-256 hash of the artifact")
    size_bytes: int = Field(..., description="Size of the artifact in bytes")
    mime_type: str | None = Field(None, description="MIME type of the artifact")
    filename: str | None = Field(None, description="Original filename of the artifact")
    source_uri: str | None = Field(None, description="URI pointing to the source of the artifact")
