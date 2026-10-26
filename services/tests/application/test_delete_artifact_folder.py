"""Deleting a document removes its whole folder, not just the uploaded file."""

from __future__ import annotations

from uuid import uuid4

import pytest
from returns.result import Success

from application.use_cases.artifact_use_cases import DeleteArtifactUseCase
from domain.aggregates.artifact import Artifact
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from tests.fakes.fake_auth import FakeAuth
from tests.mocks import MockArtifactRepository, MockPageRepository

WS = uuid4()


class RecordingBlobStore:
    def __init__(self) -> None:
        self.deleted_prefixes: list[str] = []
        self.deleted_keys: list[str] = []

    def delete_prefix(self, prefix: str) -> None:
        self.deleted_prefixes.append(prefix)

    def delete(self, key: str) -> None:
        self.deleted_keys.append(key)


def _artifact(workspace_id) -> Artifact:
    aid = uuid4()
    return Artifact.create(
        source_uri=None,
        source_filename="paper.pdf",
        artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF,
        storage_location=f"workspaces/{workspace_id}/artifacts/{aid}/source.pdf",
        artifact_id=aid,
        workspace_id=workspace_id,
    )


async def _delete(artifact: Artifact, auth) -> tuple[object, RecordingBlobStore]:
    repo = MockArtifactRepository()
    repo.save(artifact)
    blob = RecordingBlobStore()
    use_case = DeleteArtifactUseCase(repo, MockPageRepository(), blob_store=blob)
    return await use_case.execute(artifact.id, auth=auth), blob


@pytest.mark.asyncio
async def test_delete_removes_the_artifact_folder() -> None:
    artifact = _artifact(WS)

    result, blob = await _delete(artifact, FakeAuth(workspace_id=WS))

    assert isinstance(result, Success)
    assert blob.deleted_prefixes == [f"workspaces/{WS}/artifacts/{artifact.id}"]
    assert blob.deleted_keys == []


@pytest.mark.asyncio
async def test_delete_without_a_workspace_skips_the_folder_delete() -> None:
    artifact = _artifact(None)

    result, blob = await _delete(artifact, None)

    assert isinstance(result, Success)
    assert blob.deleted_prefixes == []
