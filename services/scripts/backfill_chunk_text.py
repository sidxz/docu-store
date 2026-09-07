"""Backfill ``chunk_text`` onto existing page_embeddings points.

Payload-only. Point ids are deterministic — ``uuid5(NAMESPACE_URL,
f"{page_id}:chunk:{i}")`` — so this sets a field on points that already exist:
no vectors are recomputed, no points are created or deleted, and no page ids
change. That is why it sidesteps the purge-and-rebuild that blocks a full
re-embed.

Chunk texts are re-derived from the persisted IR blob with the same
``chunk_blocks(max_chars=settings.chunk_size)`` call the embed path uses, so the
result is byte-identical *provided CHUNK_SIZE has not changed since the page was
embedded*. The stored ``chunk_count`` is the guard: a page whose re-chunk yields
a different count is skipped rather than written with misaligned text, and those
points keep the page-prefix fallback in ``rerank_passage``.

Pages with no IR blob (char-fallback embeds) have no block chunks to re-derive
and are skipped for the same reason.

Usage:
    uv run python scripts/backfill_chunk_text.py                  # dry run, whole collection
    uv run python scripts/backfill_chunk_text.py --apply          # write
    uv run python scripts/backfill_chunk_text.py <artifact_id>... # limit scope
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from uuid import NAMESPACE_URL, UUID, uuid5

import structlog
from qdrant_client import AsyncQdrantClient, models

from application.dtos.parsed_document import ParsedDocument
from application.ports.blob_store import BlobStore
from infrastructure.config import settings
from infrastructure.di.container import create_container
from infrastructure.text_chunkers.block_aware_chunker import chunk_blocks

logger = structlog.get_logger()

SCROLL_BATCH = 1000
WRITE_BATCH = 100

# Page identity as scrolled out of Qdrant: what we need to re-derive its chunks.
_FIELDS = ["page_id", "artifact_id", "page_index", "chunk_count"]


async def scan_pages(
    client: AsyncQdrantClient,
    artifact_ids: set[str] | None,
) -> dict[str, tuple[str, int, int]]:
    """page_id -> (artifact_id, page_index, chunk_count), one entry per page."""
    pages: dict[str, tuple[str, int, int]] = {}
    offset = None
    scanned = 0
    while True:
        points, offset = await client.scroll(
            collection_name=settings.qdrant_collection_name,
            limit=SCROLL_BATCH,
            offset=offset,
            with_payload=_FIELDS,
            with_vectors=False,
        )
        for p in points:
            scanned += 1
            pl = p.payload or {}
            pid, aid = pl.get("page_id"), pl.get("artifact_id")
            if not pid or not aid or (artifact_ids and aid not in artifact_ids):
                continue
            if pid not in pages:
                pages[pid] = (aid, pl.get("page_index", 0), pl.get("chunk_count") or 0)
        if offset is None:
            break
    logger.info("scan_complete", points=scanned, pages=len(pages))
    return pages


def page_chunk_texts(doc: ParsedDocument, page_index: int) -> list[str]:
    """Re-derive one page's chunk texts exactly as the embed path builds them."""
    blocks = [b for b in doc.blocks if b.source_page_index == page_index]
    if not blocks:
        return []
    return [
        bc.text
        for bc in chunk_blocks(blocks, max_chars=settings.chunk_size)
        if bc.text.strip()
    ]


async def flush(client: AsyncQdrantClient, ops: list, apply: bool) -> None:
    if ops and apply:
        await client.batch_update_points(
            collection_name=settings.qdrant_collection_name,
            update_operations=ops,
        )
    ops.clear()


async def run(artifact_ids: list[str], apply: bool) -> None:
    container = create_container()
    blob_store = container[BlobStore]
    client = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60)

    try:
        pages = await scan_pages(client, set(artifact_ids) or None)

        by_artifact: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
        for page_id, (aid, page_index, chunk_count) in pages.items():
            by_artifact[aid].append((page_id, page_index, chunk_count))

        written = skipped_count = skipped_blob = 0
        ops: list = []

        for aid, page_rows in by_artifact.items():
            key = f"artifacts/{aid}/parsed/document.json"
            try:
                if not blob_store.exists(key):
                    skipped_blob += len(page_rows)
                    continue
                doc = ParsedDocument.model_validate_json(blob_store.get_bytes(key))
            except Exception:
                logger.warning("ir_read_failed", artifact_id=aid)
                skipped_blob += len(page_rows)
                continue

            for page_id, page_index, chunk_count in page_rows:
                texts = page_chunk_texts(doc, page_index)
                # The guard: misaligned indices would write the wrong passage
                # onto every chunk of the page, which is worse than not writing.
                if not texts or len(texts) != chunk_count:
                    logger.warning(
                        "chunk_count_mismatch",
                        page_id=page_id,
                        stored=chunk_count,
                        rederived=len(texts),
                    )
                    skipped_count += 1
                    continue
                for i, text in enumerate(texts):
                    ops.append(
                        models.SetPayloadOperation(
                            set_payload=models.SetPayload(
                                payload={"chunk_text": text},
                                points=[str(uuid5(NAMESPACE_URL, f"{UUID(page_id)}:chunk:{i}"))],
                            ),
                        ),
                    )
                    written += 1
                if len(ops) >= WRITE_BATCH:
                    await flush(client, ops, apply)

        await flush(client, ops, apply)
        logger.info(
            "backfill_complete",
            mode="apply" if apply else "dry-run",
            points_written=written,
            pages_skipped_count_mismatch=skipped_count,
            pages_skipped_no_ir=skipped_blob,
        )
    finally:
        await client.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact_ids", nargs="*", help="limit to these artifacts")
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = ap.parse_args()
    asyncio.run(run(args.artifact_ids, args.apply))
