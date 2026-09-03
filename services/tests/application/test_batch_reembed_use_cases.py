import pytest
from uuid import uuid4

from application.dtos.parsed_document import Block, ParsedDocument
from application.use_cases.batch_reembed_use_cases import BatchReEmbedArtifactPagesUseCase
from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from domain.value_objects.source_class import SourceClass
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_class",
    [SourceClass.INTERNAL, SourceClass.LITERATURE_OA],
)
async def test_batch_reembed_writes_provenance(source_class):
    """The path the ingestion pipeline actually runs must carry source_class.

    This is the regression: provenance went into the single-page embedding use
    case, the pipeline runs the batch one, and every point was written without
    it. Both build the payload through build_page_payload now, and this pins the
    half that ships.
    """
    artifact_repo, page_repo = MockArtifactRepository(), MockPageRepository()
    artifact = Artifact.create(
        source_uri="https://doi.org/10.1021/acsinfecdis.4c00808",
        source_filename="PMC11915372.pdf",
        artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF,
        storage_location="artifacts/x/source.pdf",
        source_class=source_class,
        licence="cc by",
    )
    page = Page.create(name="P1", artifact_id=artifact.id, index=0)
    page.update_text_mention(TextMention(text="Pks13 inhibitors of the benzofuran series"))
    artifact.add_pages([page.id])
    artifact_repo.artifacts[artifact.id] = artifact
    page_repo.pages[page.id] = page

    vs = MockVectorStore()
    uc = BatchReEmbedArtifactPagesUseCase(
        artifact_repository=artifact_repo, page_repository=page_repo,
        embedding_generator=MockEmbeddingGenerator(), vector_store=vs,
        text_chunker=MockTextChunker(),
    )
    out = await uc.execute(artifact.id)

    assert out["status"] == "success"
    assert vs.upsert_chunk_calls[-1]["metadata"]["source_class"] == source_class


@pytest.mark.asyncio
async def test_batch_reembed_writes_artifact_tags():
    """A re-embed must lay down artifact_tag_normalized itself.

    The regression: SyncArtifactMetadataToVectorStoreUseCase patched this field
    onto existing points, but upsert_page_chunk_embeddings deletes and recreates
    them -- and the batch re-embed runs at the *end* of ingestion, after tag
    aggregation. So every fully-ingested artifact lost its artifact-level tags,
    and the "any" tag-match mode (page tags OR artifact tags) silently collapsed
    to page-tags-only. A page that never spells out the document's own topic
    became unreachable by a query filtered on that topic.
    """
    artifact_repo, page_repo = MockArtifactRepository(), MockPageRepository()
    artifact = Artifact.create(
        source_uri="https://doi.org/10.1021/jm500204s",
        source_filename="mrsa.pdf",
        artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF,
        storage_location="artifacts/x/source.pdf",
        source_class=SourceClass.INTERNAL,
        licence="cc by",
    )
    artifact.update_tag_mentions([TagMention(tag="MRSA", entity_type="disease")])
    # The page's own text never says MRSA -- only the artifact-level tag can match it.
    page = Page.create(name="P6", artifact_id=artifact.id, index=5)
    page.update_text_mention(TextMention(text="CHEMBL3265193 13.6 | CHEMBL3265194 18.1"))
    artifact.add_pages([page.id])
    artifact_repo.artifacts[artifact.id] = artifact
    page_repo.pages[page.id] = page

    vs = MockVectorStore()
    uc = BatchReEmbedArtifactPagesUseCase(
        artifact_repository=artifact_repo, page_repository=page_repo,
        embedding_generator=MockEmbeddingGenerator(), vector_store=vs,
        text_chunker=MockTextChunker(),
    )
    out = await uc.execute(artifact.id)

    assert out["status"] == "success"
    assert vs.upsert_chunk_calls[-1]["metadata"]["artifact_tag_normalized"] == ["mrsa"]
