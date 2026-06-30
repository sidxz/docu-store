import io

from returns.result import Failure, Success

from application.dtos.blob_dtos import UploadBlobRequest
from application.ports.blob_store import StoredBlob
from application.use_cases.blob_use_cases import UploadBlobUseCase
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType


class FakeBlobStore:
    def put_stream(self, key, stream, *, mime_type=None):
        data = stream.read()
        return StoredBlob(key=key, size_bytes=len(data), sha256="x", mime_type=mime_type)


def _req(mime):
    return UploadBlobRequest(
        artifact_type=ArtifactType.RESEARCH_ARTICLE, filename="deck", mime_type=mime
    )


def test_upload_accepts_pdf():
    uc = UploadBlobUseCase(blob_store=FakeBlobStore())
    assert isinstance(uc.execute(io.BytesIO(b"d"), _req(MimeType.PDF.value)), Success)


def test_upload_accepts_pptx():
    uc = UploadBlobUseCase(blob_store=FakeBlobStore())
    assert isinstance(uc.execute(io.BytesIO(b"d"), _req(MimeType.PPTX.value)), Success)


def test_upload_accepts_docx():
    uc = UploadBlobUseCase(blob_store=FakeBlobStore())
    assert isinstance(uc.execute(io.BytesIO(b"d"), _req(MimeType.DOCX.value)), Success)


def test_upload_rejects_unsupported_mime():
    uc = UploadBlobUseCase(blob_store=FakeBlobStore())
    assert isinstance(uc.execute(io.BytesIO(b"d"), _req("text/plain")), Failure)
