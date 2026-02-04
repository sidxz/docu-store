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
