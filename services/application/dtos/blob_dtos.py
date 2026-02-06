from uuid import UUID

from pydantic import BaseModel, Field

from domain.value_objects.artifact_type import ArtifactType


class UploadBlobRequest(BaseModel):
    source_uri: str | None = Field(None, description="URI pointing to the source of the artifact")
    artifact_type: ArtifactType = Field(..., description="Classification type of the artifact")
    filename: str | None = Field(None, description="Original filename of the artifact")
    mime_type: str | None


class UploadBlobResponse(BaseModel):
    artifact_id: UUID = Field(..., description="Unique identifier of the artifact")
    storage_key: str = Field(..., description="Storage key of the artifact")
    sha256: str = Field(..., description="SHA-256 hash of the artifact")
    size_bytes: int = Field(..., description="Size of the artifact in bytes")
    mime_type: str | None = Field(None, description="MIME type of the artifact")
    filename: str | None = Field(None, description="Original filename of the artifact")
    source_uri: str | None = Field(None, description="URI pointing to the source of the artifact")
