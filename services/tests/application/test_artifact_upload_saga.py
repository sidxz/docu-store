"""Tests for ArtifactUploadSaga — thinned (no synchronous parsing)."""

from __future__ import annotations

import io

import pytest
from returns.result import Success

from application.dtos.blob_dtos import UploadBlobRequest
from application.sagas.artifact_upload_saga import ArtifactUploadSaga
from application.use_cases.artifact_use_cases import CreateArtifactUseCase
from application.use_cases.blob_use_cases import UploadBlobUseCase
from domain.value_objects.artifact_type import ArtifactType
from tests.mocks import MockArtifactRepository


class FakeBlobStore:
    def __init__(self):
        self.puts: dict[str, bytes] = {}

    def put_stream(self, key, stream, *, mime_type=None):
        self.puts[key] = stream.read()
        from application.ports.blob_store import StoredBlob

        return StoredBlob(key=key, size_bytes=len(self.puts[key]), sha256="x", mime_type=mime_type)


class FakePermissionRegistrar:
    async def register_resource(self, **kwargs):
        pass


class _ParseSpy:
    pdf_parse_count: int = 0


@pytest.fixture
def saga_under_test():
    blob = FakeBlobStore()
    artifact_repo = MockArtifactRepository()
    registrar = FakePermissionRegistrar()
    calls = _ParseSpy()

    saga = ArtifactUploadSaga(
        upload_blob_use_case=UploadBlobUseCase(blob_store=blob),
        create_artifact_use_case=CreateArtifactUseCase(artifact_repo),
        permission_registrar=registrar,
    )
    return saga, calls


@pytest.mark.asyncio
async def test_saga_uploads_and_creates_artifact_without_parsing(saga_under_test):
    saga, calls = saga_under_test
    req = UploadBlobRequest(
        artifact_type=ArtifactType.RESEARCH_ARTICLE,
        filename="x.pdf",
        mime_type="application/pdf",
    )
    result = await saga.execute(io.BytesIO(b"%PDF-1.4 ..."), req)
    assert isinstance(result, Success)
    artifact = result.unwrap()
    assert artifact.pages in (None, [])  # no pages created synchronously
    assert calls.pdf_parse_count == 0  # saga never parses
