from uuid import UUID

from pydantic import BaseModel


class UploadBlobRequest(BaseModel):
    filename: str | None
    mime_type: str | None


class UploadBlobResponse(BaseModel):
    storage_key: str
    sha256: str
    size_bytes: int
    mime_type: str | None
    filename: str | None


class BlobUploadedEvent(BaseModel):
    """Event emitted when a blob is uploaded - used to trigger workflows."""

    storage_key: str
    filename: str | None
    mime_type: str | None
    size_bytes: int
    artifact_id: UUID
