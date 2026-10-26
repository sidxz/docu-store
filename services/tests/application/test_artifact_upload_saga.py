"""Tests for ArtifactUploadSaga — thinned (no synchronous parsing)."""

from __future__ import annotations

import io
from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.blob_dtos import UploadBlobRequest
from application.dtos.errors import AppError
from application.sagas.artifact_upload_saga import ArtifactUploadSaga
from application.use_cases.artifact_use_cases import CreateArtifactUseCase
from application.use_cases.blob_use_cases import UploadBlobUseCase
from domain.value_objects.artifact_type import ArtifactType
from tests.fakes.fake_auth import FakeAuth
from tests.mocks import MockArtifactRepository

WS = uuid4()
AUTH = FakeAuth(role="editor", workspace_id=WS)
REQ = UploadBlobRequest(
    artifact_type=ArtifactType.RESEARCH_ARTICLE,
    filename="x.pdf",
    mime_type="application/pdf",
)


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


@pytest.fixture
def saga_under_test():
    blob = FakeBlobStore()
    artifact_repo = MockArtifactRepository()
    registrar = FakePermissionRegistrar()

    saga = ArtifactUploadSaga(
        upload_blob_use_case=UploadBlobUseCase(blob_store=blob),
        create_artifact_use_case=CreateArtifactUseCase(artifact_repo),
        permission_registrar=registrar,
    )
    return saga, artifact_repo, blob


@pytest.mark.asyncio
async def test_saga_uploads_and_creates_artifact_without_parsing(saga_under_test):
    saga, artifact_repo, _ = saga_under_test
    result = await saga.execute(io.BytesIO(b"%PDF-1.4 ..."), REQ, auth=AUTH)
    assert isinstance(result, Success)
    artifact = result.unwrap()
    assert artifact.pages in (None, [])  # no pages created synchronously
    assert artifact_repo.save_called  # artifact persisted to repo


@pytest.mark.asyncio
async def test_upload_keeps_the_source_in_the_artifacts_own_folder(saga_under_test):
    saga, _, blob = saga_under_test
    art = (await saga.execute(io.BytesIO(b"%PDF-1.4 x"), REQ, auth=AUTH)).unwrap()
    (key,) = blob.puts
    assert key == f"workspaces/{WS}/artifacts/{art.artifact_id}/source.pdf"
    assert art.storage_location == key


@pytest.mark.asyncio
async def test_upload_without_a_workspace_is_refused(saga_under_test):
    saga, _, blob = saga_under_test
    result = await saga.execute(io.BytesIO(b"%PDF-1.4 x"), REQ, auth=None)
    assert isinstance(result, Failure)
    assert result.failure().category == "validation"
    assert blob.puts == {}


@pytest.mark.asyncio
async def test_upload_records_the_uploaded_size(saga_under_test):
    saga, _, _ = saga_under_test
    payload = b"%PDF-1.4 fifteen"
    art = (await saga.execute(io.BytesIO(payload), REQ, auth=AUTH)).unwrap()
    assert art.source_size_bytes == len(payload)


class FakeQuota:
    def __init__(self, result) -> None:
        self._result = result
        self.calls: list[tuple] = []

    async def execute(self, workspace_id, incoming_bytes):
        self.calls.append((workspace_id, incoming_bytes))
        return self._result


def _saga_with_quota(quota):
    blob, repo = FakeBlobStore(), MockArtifactRepository()
    saga = ArtifactUploadSaga(
        upload_blob_use_case=UploadBlobUseCase(blob_store=blob),
        create_artifact_use_case=CreateArtifactUseCase(repo),
        permission_registrar=FakePermissionRegistrar(),
        storage_quota=quota,
    )
    return saga, repo, blob


FULL = Failure(AppError("storage_full", "This workspace is out of storage."))


@pytest.mark.asyncio
async def test_refused_upload_writes_nothing():
    saga, repo, blob = _saga_with_quota(FakeQuota(FULL))
    result = await saga.execute(io.BytesIO(b"%PDF-1.4 x"), REQ, auth=AUTH)
    assert isinstance(result, Failure)
    assert result.failure().category == "storage_full"
    assert blob.puts == {}
    assert not repo.save_called


@pytest.mark.asyncio
async def test_admins_are_not_exempt():
    saga, _, _ = _saga_with_quota(FakeQuota(FULL))
    admin = FakeAuth(role="admin", workspace_id=WS)
    result = await saga.execute(io.BytesIO(b"%PDF-1.4 x"), REQ, auth=admin)
    assert isinstance(result, Failure)


@pytest.mark.asyncio
async def test_quota_sees_the_stream_size():
    quota = FakeQuota(Success(None))
    saga, _, blob = _saga_with_quota(quota)
    payload = b"%PDF-1.4 seventeen"
    await saga.execute(io.BytesIO(payload), REQ, auth=AUTH)
    assert quota.calls == [(WS, len(payload))]
    assert list(blob.puts.values()) == [payload]
