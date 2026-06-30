import pytest
from uuid import uuid4

from application.dtos.parsed_document import Block, ParsedDocument
from application.use_cases.batch_reembed_use_cases import BatchReEmbedArtifactPagesUseCase
from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.text_mention import TextMention
from tests.mocks import (
    MockArtifactRepository, MockEmbeddingGenerator, MockPageRepository,
    MockTextChunker, MockVectorStore,
)


class _IRBlobStore:
    def __init__(self, artifact_id, blocks):
        self._key = f"artifacts/{artifact_id}/parsed/document.json"
        self._doc = ParsedDocument(source_mime="application/pdf", blocks=blocks)

    def exists(self, key): return key == self._key

    def get_bytes(self, key): return self._doc.model_dump_json().encode()


@pytest.mark.asyncio
async def test_batch_reembed_block_aware_when_ir_present():
    artifact_repo, page_repo = MockArtifactRepository(), MockPageRepository()
    # one artifact, one page with text
    artifact = Artifact.create(
        source_uri="https://example.com/paper.pdf",
        source_filename="paper.pdf",
        artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF,
        storage_location="artifacts/x/source.pdf",
    )
    page = Page.create(name="P1", artifact_id=artifact.id, index=0)
    page.update_text_mention(TextMention(text="fallback text"))
    artifact.add_pages([page.id])
    artifact_repo.artifacts[artifact.id] = artifact
    page_repo.pages[page.id] = page

    blocks = [
        Block(type="table", rows=[["Cmpd", "IC50"], ["X", "5 nM"]],
              caption="T1", section_path=["Results"], source_page_index=0),
    ]
    vs = MockVectorStore()
    uc = BatchReEmbedArtifactPagesUseCase(
        artifact_repository=artifact_repo, page_repository=page_repo,
        embedding_generator=MockEmbeddingGenerator(), vector_store=vs,
        text_chunker=MockTextChunker(), blob_store=_IRBlobStore(artifact.id, blocks),
    )
    out = await uc.execute(artifact.id)
    assert out["status"] == "success"
    cm = vs.upsert_chunk_calls[-1]["chunk_metadata"]
    assert cm is not None and any(m["is_table"] for m in cm)


@pytest.mark.asyncio
async def test_batch_reembed_scopes_table_tags():
    artifact_repo, page_repo = MockArtifactRepository(), MockPageRepository()
    artifact = Artifact.create(
        source_uri="https://example.com/paper.pdf",
        source_filename="paper.pdf",
        artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF,
        storage_location="artifacts/x/source.pdf",
    )
    page = Page.create(name="P1", artifact_id=artifact.id, index=0)
    page.update_text_mention(TextMention(text="Rho in the intro; PptT assay table below."))
    page.update_tag_mentions([
        TagMention(tag="PptT", entity_type="target"),
        TagMention(tag="Rho", entity_type="target"),
    ])
    artifact.add_pages([page.id])
    artifact_repo.artifacts[artifact.id] = artifact
    page_repo.pages[page.id] = page

    blocks = [
        Block(type="table", rows=[["Cmpd", "IC50"], ["X", "5 nM"]],
              caption="Table 1. PptT inhibition", section_path=["Results"],
              source_page_index=0),
    ]
    vs = MockVectorStore()
    uc = BatchReEmbedArtifactPagesUseCase(
        artifact_repository=artifact_repo, page_repository=page_repo,
        embedding_generator=MockEmbeddingGenerator(), vector_store=vs,
        text_chunker=MockTextChunker(), blob_store=_IRBlobStore(artifact.id, blocks),
    )
    out = await uc.execute(artifact.id)
    assert out["status"] == "success"
    cm = vs.upsert_chunk_calls[-1]["chunk_metadata"]
    table_meta = next(m for m in cm if m.get("is_table"))
    assert table_meta["tag_normalized"] == ["pptt"]
    assert "rho" not in table_meta["tag_normalized"]
