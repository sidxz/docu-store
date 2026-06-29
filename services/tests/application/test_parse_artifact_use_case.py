import io
from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.artifact_dtos import CreateArtifactRequest
from application.dtos.errors import AppError
from application.dtos.parsed_document import Block, ParsedDocument, ParseResult, RenderedPage
from application.use_cases.artifact_use_cases import AddPagesUseCase, CreateArtifactUseCase
from application.use_cases.page_use_cases import CreatePageUseCase, UpdateTextMentionUseCase
from application.use_cases.parse_artifact_use_case import ParseArtifactUseCase, page_id_for
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from tests.mocks import MockArtifactRepository, MockPageRepository


class FakeParser:
    def parse(self, storage_key):
        doc = ParsedDocument(source_mime="application/pdf", blocks=[
            Block(type="paragraph", text="hello", source_page_index=0),
        ])
        return ParseResult(document=doc, pages=[RenderedPage(index=0, png=b"img", thumb=b"t")])


class FakeBlobStore:
    def __init__(self):
        self.puts: dict[str, bytes] = {}

    def put_stream(self, key, stream, *, mime_type=None):
        self.puts[key] = stream.read()
        from application.ports.blob_store import StoredBlob
        return StoredBlob(key=key, size_bytes=len(self.puts[key]), sha256="x", mime_type=mime_type)


async def _make_artifact(artifact_repo):
    uc = CreateArtifactUseCase(artifact_repo)
    req = CreateArtifactRequest(
        artifact_id=uuid4(),
        artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF,
        storage_location="artifacts/x/source.pdf",
    )
    return (await uc.execute(req)).unwrap().artifact_id


def _build_uc(parsers, blob, page_repo, artifact_repo):
    return ParseArtifactUseCase(
        parsers=parsers,
        blob_store=blob,
        artifact_repository=artifact_repo,
        page_repository=page_repo,
        create_page_use_case=CreatePageUseCase(page_repo, artifact_repo),
        update_text_mention_use_case=UpdateTextMentionUseCase(page_repo),
        add_pages_use_case=AddPagesUseCase(artifact_repo, page_repo),
    )


@pytest.mark.asyncio
async def test_parse_creates_page_stores_image_and_ir():
    page_repo, artifact_repo, blob = MockPageRepository(), MockArtifactRepository(), FakeBlobStore()
    artifact_id = await _make_artifact(artifact_repo)
    uc = _build_uc({MimeType.PDF: FakeParser()}, blob, page_repo, artifact_repo)

    result = await uc.execute(artifact_id)

    assert isinstance(result, Success)
    assert result.unwrap() == [page_id_for(artifact_id, 0)]
    assert f"artifacts/{artifact_id}/pages/0.png" in blob.puts
    assert f"artifacts/{artifact_id}/parsed/document.json" in blob.puts


@pytest.mark.asyncio
async def test_parse_is_idempotent_on_retry():
    """
    Exercises the create-Failure / existing-page branch:
    - run 1: creates page, sets text
    - run 2: create_page returns Failure (already exists), loads page, finds same text → skips update
    """
    page_repo, artifact_repo, blob = MockPageRepository(), MockArtifactRepository(), FakeBlobStore()
    artifact_id = await _make_artifact(artifact_repo)
    uc = _build_uc({MimeType.PDF: FakeParser()}, blob, page_repo, artifact_repo)

    first = await uc.execute(artifact_id)
    assert isinstance(first, Success)

    # Swap in a create_page stub that always returns Failure (simulates "already exists" on retry).
    class _AlwaysFailCreate:
        async def execute(self, req):
            return Failure(AppError("conflict", "already exists"))

    uc.create_page = _AlwaysFailCreate()

    # Spy on update_text_mention to count calls.
    real_update = uc.update_text_mention
    update_calls = []

    class _SpyUpdate:
        async def execute(self, **kwargs):
            update_calls.append(kwargs)
            return await real_update.execute(**kwargs)

    uc.update_text_mention = _SpyUpdate()

    second = await uc.execute(artifact_id)

    assert isinstance(second, Success)
    assert first.unwrap() == second.unwrap()
    # page_repo already holds the page with the same text from run 1 → skip re-emit
    assert update_calls == [], f"update_text_mention should not be called on clean retry, got {update_calls}"
