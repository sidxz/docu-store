"""Batch re-embed all pages of an artifact with full contextual prefixes.

After all page summaries are complete, this use case re-embeds every page's
chunks in a single batch call — much faster than 100 individual re-embed
workflows.  Sparse embeddings are NOT regenerated (they use raw text, not
the contextual prefix).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog

if TYPE_CHECKING:
    from application.ports.compound_vector_store import CompoundVectorStore
    from application.ports.embedding_generator import EmbeddingGenerator
    from application.ports.repositories.artifact_repository import ArtifactRepository
    from application.ports.repositories.page_repository import PageRepository
    from application.ports.summary_vector_store import SummaryVectorStore
    from application.ports.text_chunker import TextChunker
    from application.ports.vector_store import VectorStore
    from domain.aggregates.page import Page

logger = structlog.get_logger()

# Process pages in batches to bound memory usage on very large documents.
_PAGE_BATCH_SIZE = 50


class BatchReEmbedArtifactPagesUseCase:
    """Re-embed all pages of an artifact in one batch.

    Loads all pages, builds contextual prefixes (title + tags + summary),
    batch-encodes all chunks with the embedding model, and upserts to Qdrant.
    Sparse embeddings are skipped (they don't use the context prefix).
    """

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        page_repository: PageRepository,
        embedding_generator: EmbeddingGenerator,
        vector_store: VectorStore,
        text_chunker: TextChunker,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.page_repository = page_repository
        self.embedding_generator = embedding_generator
        self.vector_store = vector_store
        self.text_chunker = text_chunker

    @staticmethod
    def _build_chunk_context(
        artifact_title: str | None,
        page: Page,
    ) -> str:
        """Build a context prefix for a page's chunks."""
        parts = []
        if artifact_title:
            parts.append(f"Document: {artifact_title}")
        if page.tag_mentions:
            tags = [tm.tag for tm in page.tag_mentions[:10]]
            parts.append(f"Tags: {', '.join(tags)}")
        parts.append(f"Page {page.index + 1}")
        if page.summary_candidate and page.summary_candidate.summary:
            parts.append(f"Summary: {page.summary_candidate.summary[:200]}")
        return " | ".join(parts) + "\n\n" if parts else ""

    def _build_page_metadata(self, page: Page) -> dict:
        """Build Qdrant payload metadata for a page."""
        metadata: dict = {}
        if page.workspace_id:
            metadata["workspace_id"] = str(page.workspace_id)
        if page.tag_mentions:
            metadata["tags"] = [tm.tag for tm in page.tag_mentions]
            metadata["tag_normalized"] = [tm.tag.lower() for tm in page.tag_mentions]
            ner_types = {tm.entity_type for tm in page.tag_mentions if tm.entity_type}
            metadata["entity_types"] = sorted(ner_types)
        if page.compound_mentions:
            metadata["compound_smiles"] = [
                cm.canonical_smiles
                for cm in page.compound_mentions
                if cm.canonical_smiles and cm.is_smiles_valid
            ]
        return metadata

    async def execute(self, artifact_id: UUID) -> dict:
        """Re-embed all pages of an artifact with full contextual prefixes.

        Returns:
            Summary dict with page_count, chunk_count, status.

        """
        logger.info("batch_reembed_start", artifact_id=str(artifact_id))

        artifact = self.artifact_repository.get_by_id(artifact_id)
        artifact_title = artifact.title_mention.title if artifact.title_mention else None

        if not artifact.pages:
            logger.info("batch_reembed_no_pages", artifact_id=str(artifact_id))
            return {"status": "skipped", "reason": "no_pages", "page_count": 0}

        total_pages = 0
        total_chunks = 0

        # Process pages in batches to bound memory
        for batch_start in range(0, len(artifact.pages), _PAGE_BATCH_SIZE):
            batch_page_ids = artifact.pages[batch_start : batch_start + _PAGE_BATCH_SIZE]
            pages_processed, chunks_processed = await self._process_page_batch(
                batch_page_ids,
                artifact_title,
                artifact_id,
            )
            total_pages += pages_processed
            total_chunks += chunks_processed

        logger.info(
            "batch_reembed_complete",
            artifact_id=str(artifact_id),
            page_count=total_pages,
            chunk_count=total_chunks,
        )

        return {
            "status": "success",
            "artifact_id": str(artifact_id),
            "page_count": total_pages,
            "chunk_count": total_chunks,
        }

    async def _process_page_batch(
        self,
        page_ids: list[UUID],
        artifact_title: str | None,
        artifact_id: UUID,
    ) -> tuple[int, int]:
        """Process a batch of pages: chunk, encode, upsert.

        Returns:
            (pages_processed, chunks_processed)

        """
        # Collect all chunks across pages in this batch
        page_chunk_groups: list[tuple[Page, list]] = []
        all_contextual_texts: list[str] = []

        for page_id in page_ids:
            page = self.page_repository.get_by_id(page_id)
            if not page.text_mention or not page.text_mention.text:
                continue

            chunks = self.text_chunker.chunk_text(page.text_mention.text)
            from infrastructure.config import settings as _settings

            context_prefix = (
                self._build_chunk_context(artifact_title, page)
                if _settings.embedding_enable_context_enrichment
                else ""
            )

            for chunk in chunks:
                all_contextual_texts.append(context_prefix + chunk.text)

            page_chunk_groups.append((page, chunks))

        if not all_contextual_texts:
            return 0, 0

        # ONE batch encode for all chunks across all pages in this batch
        embeddings = await self.embedding_generator.generate_batch_embeddings(
            texts=all_contextual_texts,
        )

        # Distribute embeddings back to pages and upsert per-page
        embedding_offset = 0
        for page, chunks in page_chunk_groups:
            page_embedding_count = len(chunks)
            page_embeddings = embeddings[embedding_offset : embedding_offset + page_embedding_count]
            embedding_offset += page_embedding_count

            metadata = self._build_page_metadata(page)

            # Upsert per-page (sparse_embeddings=None — we skip sparse on re-embed)
            await self.vector_store.upsert_page_chunk_embeddings(
                page_id=page.id,
                artifact_id=artifact_id,
                embeddings=page_embeddings,
                page_index=page.index,
                chunk_count=page_embedding_count,
                metadata=metadata or None,
                sparse_embeddings=None,
            )

        return len(page_chunk_groups), len(all_contextual_texts)


class BatchReEmbedSmilesUseCase:
    """Re-embed all SMILES/compound embeddings for an artifact.

    Iterates all pages, collects valid compounds, batch-encodes their
    canonical SMILES with ChemBERTa, and upserts to compound_embeddings.
    Does NOT update aggregates — metadata already exists from the original pipeline.
    """

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        page_repository: PageRepository,
        smiles_embedding_generator: EmbeddingGenerator,
        compound_vector_store: CompoundVectorStore,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.page_repository = page_repository
        self.smiles_embedding_generator = smiles_embedding_generator
        self.compound_vector_store = compound_vector_store

    async def execute(self, artifact_id: UUID) -> dict:
        logger.info("batch_reembed_smiles_start", artifact_id=str(artifact_id))

        artifact = self.artifact_repository.get_by_id(artifact_id)
        if not artifact.pages:
            return {"status": "skipped", "reason": "no_pages", "page_count": 0}

        total_pages = 0
        total_compounds = 0

        for batch_start in range(0, len(artifact.pages), _PAGE_BATCH_SIZE):
            batch_page_ids = artifact.pages[batch_start : batch_start + _PAGE_BATCH_SIZE]
            for page_id in batch_page_ids:
                page = self.page_repository.get_by_id(page_id)
                valid_compounds = [
                    c
                    for c in (page.compound_mentions or [])
                    if c.is_smiles_valid and c.canonical_smiles
                ]
                if not valid_compounds:
                    continue

                smiles_strings = [c.canonical_smiles for c in valid_compounds]
                embeddings = await self.smiles_embedding_generator.generate_batch_embeddings(
                    texts=smiles_strings,
                )

                compound_dicts = [
                    {
                        "smiles": c.smiles,
                        "canonical_smiles": c.canonical_smiles,
                        "extracted_id": c.extracted_id,
                        "confidence": c.confidence,
                        "is_smiles_valid": c.is_smiles_valid,
                    }
                    for c in valid_compounds
                ]

                await self.compound_vector_store.upsert_compound_embeddings(
                    page_id=page.id,
                    artifact_id=artifact_id,
                    page_index=page.index,
                    compounds=compound_dicts,
                    embeddings=embeddings,
                    workspace_id=page.workspace_id,
                )

                total_pages += 1
                total_compounds += len(valid_compounds)

        logger.info(
            "batch_reembed_smiles_complete",
            artifact_id=str(artifact_id),
            page_count=total_pages,
            compound_count=total_compounds,
        )
        return {
            "status": "success",
            "artifact_id": str(artifact_id),
            "page_count": total_pages,
            "compound_count": total_compounds,
        }


class BatchReEmbedSummariesUseCase:
    """Re-embed all summary embeddings for an artifact.

    Embeds each page summary and the artifact summary into summary_embeddings.
    Does NOT update aggregates — metadata already exists from the original pipeline.
    """

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        page_repository: PageRepository,
        embedding_generator: EmbeddingGenerator,
        summary_vector_store: SummaryVectorStore,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.page_repository = page_repository
        self.embedding_generator = embedding_generator
        self.summary_vector_store = summary_vector_store

    async def execute(self, artifact_id: UUID) -> dict:
        logger.info("batch_reembed_summaries_start", artifact_id=str(artifact_id))

        artifact = self.artifact_repository.get_by_id(artifact_id)
        artifact_title = artifact.title_mention.title if artifact.title_mention else None

        page_summary_count = 0

        if artifact.pages:
            for batch_start in range(0, len(artifact.pages), _PAGE_BATCH_SIZE):
                batch_page_ids = artifact.pages[batch_start : batch_start + _PAGE_BATCH_SIZE]
                for page_id in batch_page_ids:
                    page = self.page_repository.get_by_id(page_id)
                    if not page.summary_candidate or not page.summary_candidate.summary:
                        continue

                    summary_text = page.summary_candidate.summary
                    embedding = await self.embedding_generator.generate_text_embedding(
                        text=summary_text,
                    )

                    await self.summary_vector_store.upsert_page_summary_embedding(
                        page_id=page_id,
                        artifact_id=artifact_id,
                        embedding=embedding,
                        summary_text=summary_text,
                        artifact_title=artifact_title,
                        page_index=page.index,
                        workspace_id=page.workspace_id,
                        tags=[tm.tag for tm in page.tag_mentions] if page.tag_mentions else None,
                        entity_types=(
                            sorted({tm.entity_type for tm in page.tag_mentions if tm.entity_type})
                            if page.tag_mentions
                            else None
                        ),
                    )
                    page_summary_count += 1

        # Embed artifact summary if it exists
        artifact_summary_embedded = False
        if artifact.summary_candidate and artifact.summary_candidate.summary:
            summary_text = artifact.summary_candidate.summary
            embedding = await self.embedding_generator.generate_text_embedding(
                text=summary_text,
            )
            await self.summary_vector_store.upsert_artifact_summary_embedding(
                artifact_id=artifact_id,
                embedding=embedding,
                summary_text=summary_text,
                artifact_title=artifact_title,
                page_count=len(artifact.pages),
                workspace_id=artifact.workspace_id,
                tags=[tm.tag for tm in artifact.tag_mentions] if artifact.tag_mentions else None,
                entity_types=(
                    sorted({tm.entity_type for tm in artifact.tag_mentions if tm.entity_type})
                    if artifact.tag_mentions
                    else None
                ),
            )
            artifact_summary_embedded = True

        logger.info(
            "batch_reembed_summaries_complete",
            artifact_id=str(artifact_id),
            page_summary_count=page_summary_count,
            artifact_summary_embedded=artifact_summary_embedded,
        )
        return {
            "status": "success",
            "artifact_id": str(artifact_id),
            "page_summary_count": page_summary_count,
            "artifact_summary_embedded": artifact_summary_embedded,
        }
