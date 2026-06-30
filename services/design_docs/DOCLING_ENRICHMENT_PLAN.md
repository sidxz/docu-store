# Docling Structure Enrichment — Phase A+B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consume the document structure Docling already produces (captions, heading levels, section paths, table cells) to enrich ingestion text and make retrieval structure-aware — Phases A+B of `DOCLING_ENRICHMENT.md`.

**Architecture:** Phase A populates `Block.level`/`Block.caption`/`Block.section_path` in the Docling parser so captions + heading hierarchy flow into `page.text_mention.text` (a free `structflo-ner` yield boost; `linearize_blocks` already renders these fields). Phase B starts *reading* the per-artifact IR blob (`artifacts/{id}/parsed/document.json`, today write-only) at embed time: block-aware chunking that keeps tables intact and binds headings to their content, with per-chunk Qdrant payload (`block_type`, `section_path`, `is_table`, `is_figure`, `caption`) and matching search filters + reranker signal.

**Tech Stack:** Python 3.12, Docling 2.107.0 / docling-core 2.85.0, Pydantic v2, Qdrant (`qdrant_client`), `returns.result`, structlog, pytest. Package manager: `uv`.

## Global Constraints

- **Run every Python command with `uv run`** (e.g. `uv run pytest …`, `uv run ruff …`). Working dir for all commands: `/Users/sidx/workspace/docu-store/services`.
- **§3 division of labor (first-class):** Do **not** touch `structflo-cser` or feed it anything — CSER owns chemical structures from the full PDF page (`fitz`, independent of Docling). NER is fed *only* indirectly: Phase A captions land in `page.text_mention.text`, which the existing `Page.TextMentionUpdated` → NER path already consumes. No NER code changes in A or B.
- **§4 storage: zero new aggregate events, zero new read-model fields.** Structure lives in the IR blob (source of truth) + Qdrant chunk payload (search signals). Enriched text still flows via the existing `Page.TextMentionUpdated`. Do not add domain events or Mongo projections.
- **Docling API is version-pinned** to 2.107.0: `PictureItem.caption_text(doc) -> str`, `TableItem.caption_text(doc) -> str`, `SectionHeaderItem.level` (int field), `item.get_image(doc, prov_index=0)` (Phase C only). `TextItem`/`TitleItem` have **no** `level` field and **no** `caption_text`.
- **Backward compatibility:** new params are trailing + optional; default behavior (no IR blob present) must exactly match today's char-chunking path. Pre-Phase-A artifacts have no captions/section_path in their IR → block-aware chunking still works, just with sparse metadata.
- **Lint:** `uv run ruff check <changed files>` must be clean before each commit (matches the ingestion build's standard).

---

## File Structure

**Phase A**
- `application/dtos/parsed_document.py` — add `Block.section_path: list[str]`; fix `ParsedDocument.blocks` mutable default; add pure `assign_section_paths(blocks)` helper. (`linearize_blocks` already renders `level`/`caption` — no change needed there.)
- `infrastructure/file_services/docling_parser.py` — `_to_block` populates `level` (headings) + `caption` (figure/table); `parse()` calls `assign_section_paths`.

**Phase B**
- `infrastructure/text_chunkers/block_aware_chunker.py` *(new)* — `BlockChunk` dataclass + pure `chunk_blocks(blocks, *, max_chars)`.
- `application/ports/vector_store.py` + `infrastructure/vector_stores/qdrant_store.py` — `chunk_metadata` per-chunk payload param; new keyword/bool indexes; new filter fields.
- `application/use_cases/embedding_use_cases.py` — IR-read + block-aware path + per-chunk metadata + reranker enrichment; inject `blob_store`.
- `application/use_cases/batch_reembed_use_cases.py` — same IR-read/block-aware path; inject `blob_store`.
- `application/dtos/embedding_dtos.py` — `SearchRequest` gains `block_types`/`section`/`is_table`/`is_figure`.
- `infrastructure/di/container.py` — inject `blob_store` into the two embedding use cases.
- Tests under `tests/application/`, `tests/infrastructure/`.

---

## PHASE A — Capture & linearize (parser-only)

### Task A1: `Block.section_path` field + `assign_section_paths` helper

**Files:**
- Modify: `application/dtos/parsed_document.py`
- Test: `tests/application/test_parsed_document.py`

**Interfaces:**
- Produces: `Block.section_path: list[str]` (default `[]`); `assign_section_paths(blocks: list[Block]) -> None` (mutates each block's `section_path` in reading order using a heading stack). Consumed by Task A2 and Task B1.

- [ ] **Step 1: Write the failing tests** — append to `tests/application/test_parsed_document.py`:

```python
from application.dtos.parsed_document import assign_section_paths


def test_section_path_nests_headings_and_content():
    blocks = [
        Block(type="heading", text="Results", level=1),
        Block(type="heading", text="Assay", level=2),
        Block(type="paragraph", text="IC50 was 2 nM."),
        Block(type="heading", text="Discussion", level=1),
        Block(type="paragraph", text="We conclude X."),
    ]
    assign_section_paths(blocks)
    assert blocks[0].section_path == []                       # h1: no ancestors
    assert blocks[1].section_path == ["Results"]              # h2 under h1
    assert blocks[2].section_path == ["Results", "Assay"]     # content under h1>h2
    assert blocks[3].section_path == []                       # h1 pops back to root
    assert blocks[4].section_path == ["Discussion"]


def test_section_path_handles_no_level_as_level_one():
    blocks = [
        Block(type="heading", text="Title"),       # level None -> treated as 1
        Block(type="paragraph", text="body"),
    ]
    assign_section_paths(blocks)
    assert blocks[1].section_path == ["Title"]


def test_linearize_already_renders_caption_and_level():
    # Guards the Phase A premise: linearize consumes fields A2 will populate.
    out = linearize_blocks([
        Block(type="heading", text="Methods", level=2),
        Block(type="figure", caption="Figure 3: aminopyrimidine SAR vs hERG"),
        Block(type="table", rows=[["Cmpd", "IC50"], ["X", "5 nM"]], caption="Table 1: potency"),
    ])
    assert "## Methods" in out
    assert "[Figure: Figure 3: aminopyrimidine SAR vs hERG]" in out
    assert "*Table 1: potency*" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/application/test_parsed_document.py -v`
Expected: FAIL — `ImportError: cannot import name 'assign_section_paths'`.

- [ ] **Step 3: Implement the field + helper** in `application/dtos/parsed_document.py`.

Change the `Block` model and `ParsedDocument` (add `Field`-backed defaults), and add the helper after `linearize_blocks`:

```python
from pydantic import BaseModel, Field  # update existing import
```

```python
class Block(BaseModel):
    type: BlockType
    text: str = ""
    level: int | None = None             # heading depth
    rows: list[list[str]] | None = None  # table cells
    caption: str | None = None           # figure/table caption
    section_path: list[str] = Field(default_factory=list)  # enclosing heading breadcrumb
    source_page_index: int | None = None


class ParsedDocument(BaseModel):
    """Structure-only IR. JSON-serializable; persisted as a blob. No image bytes."""

    source_mime: str
    blocks: list[Block] = Field(default_factory=list)
```

Add at end of file:

```python
def assign_section_paths(blocks: list[Block]) -> None:
    """Set each block's section_path from the enclosing heading stack.

    Blocks must be in reading order. A heading's section_path is its ancestor
    headings (excluding itself); a content block's is every enclosing heading
    including the nearest one above it. Headings with no level are treated as
    level 1.
    """
    stack: list[tuple[int, str]] = []  # (level, text)
    for b in blocks:
        if b.type == "heading":
            lvl = b.level or 1
            while stack and stack[-1][0] >= lvl:
                stack.pop()
            b.section_path = [text for _, text in stack]
            stack.append((lvl, b.text))
        else:
            b.section_path = [text for _, text in stack]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/application/test_parsed_document.py -v`
Expected: PASS (all, including the pre-existing tests).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check application/dtos/parsed_document.py tests/application/test_parsed_document.py
git add application/dtos/parsed_document.py tests/application/test_parsed_document.py
git commit -m "feat(enrichment): Block.section_path + assign_section_paths (Phase A)"
```

---

### Task A2: Parser populates level / caption / section_path

**Files:**
- Modify: `infrastructure/file_services/docling_parser.py`
- Test: `tests/infrastructure/test_docling_parser_blocks.py` *(new)*

**Interfaces:**
- Consumes: `assign_section_paths` (A1), Docling `caption_text(doc)` / `SectionHeaderItem.level`.
- Produces: `DoclingParser._to_block` now sets `level` on heading blocks and `caption` on figure/table blocks; `parse()` calls `assign_section_paths(blocks)` before building the `ParsedDocument`. `_caption(item, dl_doc) -> str | None` helper.

- [ ] **Step 1: Write the failing tests** — create `tests/infrastructure/test_docling_parser_blocks.py`. Use lightweight fakes (no models loaded):

```python
"""Unit tests for DoclingParser._to_block field population (no model load)."""
from __future__ import annotations

from infrastructure.file_services.docling_parser import DoclingParser


class _Label:
    def __init__(self, value): self.value = value


class _Prov:
    def __init__(self, page_no): self.page_no = page_no


class _FakeItem:
    """Stand-in for a Docling NodeItem."""
    def __init__(self, label, *, text="", level=None, caption=None, page_no=1):
        self.label = _Label(label)
        self.text = text
        self._level = level
        self._caption = caption
        self.prov = [_Prov(page_no)]
        if level is not None:
            self.level = level

    def caption_text(self, doc):  # mirrors PictureItem/TableItem API
        return self._caption or ""


def _parser():
    return DoclingParser(blob_store=None)  # blob_store unused by _to_block/_caption


def test_to_block_sets_heading_level():
    b = _parser()._to_block(_FakeItem("section_header", text="Methods", level=2), doc=None)
    assert b.type == "heading"
    assert b.level == 2
    assert b.text == "Methods"


def test_to_block_sets_figure_caption_and_keeps_empty_text():
    b = _parser()._to_block(
        _FakeItem("picture", caption="Figure 3: SAR vs hERG"), doc=None
    )
    assert b.type == "figure"
    assert b.caption == "Figure 3: SAR vs hERG"


def test_to_block_title_has_no_level():
    b = _parser()._to_block(_FakeItem("title", text="My Paper"), doc=None)
    assert b.type == "heading"
    assert b.level is None  # TitleItem has no level field in docling 2.107


def test_caption_returns_none_when_absent():
    assert _parser()._caption(_FakeItem("picture", caption=""), doc=None) is None
```

> Note: `_to_block` / `_caption` are called with `doc=None` because the fakes don't use the doc arg. Table rows are covered separately by `tests/infrastructure/test_docling_table_rows.py`; this task does not change `_table_rows`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/infrastructure/test_docling_parser_blocks.py -v`
Expected: FAIL — figure has `caption is None` / heading has `level is None` (fields not yet populated).

- [ ] **Step 3: Implement** — edit `infrastructure/file_services/docling_parser.py`.

Add the heading-stack call in `parse()` (import the helper at top):

```python
from application.dtos.parsed_document import (
    Block, ParsedDocument, ParseResult, RenderedPage, assign_section_paths,
)
```

In `parse()`, after the `for item, _level in dl_doc.iterate_items():` loop that fills `blocks`, before building pages:

```python
        assign_section_paths(blocks)
```

Replace `_to_block` and add `_caption`:

```python
    def _to_block(self, item, dl_doc) -> Block | None:
        # item.label is a DocItemLabel enum; .value gives the string
        label_val = getattr(item.label, "value", None) if hasattr(item, "label") else None
        btype = _LABEL_MAP.get(str(label_val), "other")

        page_idx: int | None = None
        prov = getattr(item, "prov", None)
        if prov:
            page_idx = prov[0].page_no - 1  # convert 1-based to 0-based

        if btype == "table":
            return Block(
                type="table",
                rows=self._table_rows(item, dl_doc),
                caption=self._caption(item, dl_doc),
                source_page_index=page_idx,
            )

        if btype == "figure":
            return Block(
                type="figure",
                caption=self._caption(item, dl_doc),
                source_page_index=page_idx,
            )

        text = getattr(item, "text", "") or ""
        if not text:
            return None
        level = getattr(item, "level", None) if btype == "heading" else None
        return Block(type=btype, text=text, level=level, source_page_index=page_idx)

    def _caption(self, item, dl_doc) -> str | None:
        """Figure/table caption via Docling's caption_text(doc); None if absent."""
        fn = getattr(item, "caption_text", None)
        if fn is None:
            return None
        try:
            cap = fn(dl_doc)
        except Exception:
            log.warning("docling_parser.caption_failed", exc_info=True)
            return None
        return cap or None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/infrastructure/test_docling_parser_blocks.py tests/infrastructure/test_docling_table_rows.py tests/application/test_parsed_document.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check infrastructure/file_services/docling_parser.py tests/infrastructure/test_docling_parser_blocks.py
git add infrastructure/file_services/docling_parser.py tests/infrastructure/test_docling_parser_blocks.py
git commit -m "feat(enrichment): parser populates level/caption/section_path (Phase A)"
```

> **Phase A done.** New ingestions now carry captions + heading hierarchy into `page.text_mention.text` → NER mines them automatically (no NER change). Backfill (re-parse + re-embed of existing corpus) is an ops step, out of scope for this plan.

---

## PHASE B — Structure-aware retrieval

### Task B1: Block-aware chunker

**Files:**
- Create: `infrastructure/text_chunkers/block_aware_chunker.py`
- Test: `tests/infrastructure/test_block_aware_chunker.py` *(new)*

**Interfaces:**
- Consumes: `Block` + `linearize_blocks` + `_table_to_markdown` from `application.dtos.parsed_document`.
- Produces:
  - `@dataclass BlockChunk: text: str; block_type: str; section_path: list[str]; is_table: bool; is_figure: bool; caption: str | None`
  - `chunk_blocks(blocks: list[Block], *, max_chars: int = 1000) -> list[BlockChunk]`
  - `chunk_payload(c: BlockChunk) -> dict` — the single source of truth for the Qdrant per-chunk payload shape (imported by B3 **and** B4, so the payload keys never drift between the two embed paths).
  Consumed by Tasks B3, B4.

- [ ] **Step 1: Write the failing tests** — create `tests/infrastructure/test_block_aware_chunker.py`:

```python
from application.dtos.parsed_document import Block
from infrastructure.text_chunkers.block_aware_chunker import (
    BlockChunk, chunk_blocks, chunk_payload,
)


def test_chunk_payload_shape():
    c = BlockChunk(text="t", block_type="table", section_path=["Results", "Assay"],
                   is_table=True, is_figure=False, caption="Table 1")
    p = chunk_payload(c)
    assert p == {
        "block_type": "table", "is_table": True, "is_figure": False,
        "section_path": ["Results", "Assay"],
        "section_path_normalized": ["results", "assay"],
        "caption": "Table 1",
    }
    # caption omitted when absent
    assert "caption" not in chunk_payload(BlockChunk(text="t", block_type="paragraph"))


def test_table_is_one_intact_chunk():
    blocks = [Block(type="table", rows=[["Cmpd", "IC50"], ["X", "5 nM"]], caption="Table 1")]
    chunks = chunk_blocks(blocks, max_chars=1000)
    assert len(chunks) == 1
    assert chunks[0].is_table is True
    assert "| Cmpd | IC50 |" in chunks[0].text
    assert "| X | 5 nM |" in chunks[0].text  # not split across chunks
    assert chunks[0].caption == "Table 1"


def test_heading_binds_to_following_content():
    blocks = [
        Block(type="heading", text="Methods", level=1, section_path=[]),
        Block(type="paragraph", text="We did X.", section_path=["Methods"]),
        Block(type="paragraph", text="Then Y.", section_path=["Methods"]),
    ]
    chunks = chunk_blocks(blocks, max_chars=1000)
    assert len(chunks) == 1
    assert "# Methods" in chunks[0].text
    assert "We did X." in chunks[0].text and "Then Y." in chunks[0].text
    assert chunks[0].section_path == []  # chunk's path = heading's own path


def test_new_heading_starts_new_chunk():
    blocks = [
        Block(type="heading", text="A", level=1),
        Block(type="paragraph", text="aaa"),
        Block(type="heading", text="B", level=1),
        Block(type="paragraph", text="bbb"),
    ]
    chunks = chunk_blocks(blocks, max_chars=1000)
    assert len(chunks) == 2


def test_figure_is_its_own_chunk_with_caption():
    blocks = [Block(type="figure", caption="Fig 2: gel", section_path=["Results"])]
    chunks = chunk_blocks(blocks, max_chars=1000)
    assert len(chunks) == 1
    assert chunks[0].is_figure is True
    assert chunks[0].caption == "Fig 2: gel"
    assert "[Figure: Fig 2: gel]" in chunks[0].text
    assert chunks[0].section_path == ["Results"]


def test_size_cap_splits_prose_at_block_boundary():
    blocks = [Block(type="paragraph", text="x" * 400) for _ in range(4)]  # 1600 chars
    chunks = chunk_blocks(blocks, max_chars=1000)
    assert len(chunks) == 2  # 2+2 paragraphs, never mid-paragraph
    assert all(not c.is_table and not c.is_figure for c in chunks)


def test_oversized_table_splits_by_rows_repeating_header():
    body = [[f"C{i}", f"{i} nM"] for i in range(60)]
    blocks = [Block(type="table", rows=[["Cmpd", "IC50"], *body], caption="Big")]
    chunks = chunk_blocks(blocks, max_chars=300)
    assert len(chunks) > 1
    assert all(c.is_table for c in chunks)
    assert all("| Cmpd | IC50 |" in c.text for c in chunks)  # header repeated


def test_oversized_single_paragraph_char_splits():
    blocks = [Block(type="paragraph", text="y" * 2500)]
    chunks = chunk_blocks(blocks, max_chars=1000)
    assert len(chunks) == 3
    assert all(len(c.text) <= 1000 for c in chunks)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/infrastructure/test_block_aware_chunker.py -v`
Expected: FAIL — module `block_aware_chunker` does not exist.

- [ ] **Step 3: Implement** — create `infrastructure/text_chunkers/block_aware_chunker.py`:

```python
"""Block-aware chunking: keep tables intact, bind headings to their content,
cap size at block boundaries. Pure (no models, no IO). Falls back to a naive
char split only for a single oversized block.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from application.dtos.parsed_document import Block, _table_to_markdown, linearize_blocks


@dataclass
class BlockChunk:
    text: str
    block_type: str
    section_path: list[str] = field(default_factory=list)
    is_table: bool = False
    is_figure: bool = False
    caption: str | None = None


def _char_split(text: str, max_chars: int) -> list[str]:
    # ponytail: naive slice for the rare single-block overflow; upgrade to a
    # sentence-aware splitter only if oversized prose blocks prove common.
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def _table_group_chunk(header: list[str], rows: list[list[str]], b: Block) -> BlockChunk:
    md = _table_to_markdown([header, *rows])
    text = f"{md}\n\n*{b.caption}*" if b.caption else md
    return BlockChunk(
        text=text, block_type="table", section_path=b.section_path,
        is_table=True, caption=b.caption,
    )


def _table_chunks(b: Block, max_chars: int) -> list[BlockChunk]:
    rows = b.rows or []
    if not rows:
        if b.caption:
            return [BlockChunk(text=b.caption, block_type="table",
                               section_path=b.section_path, is_table=True, caption=b.caption)]
        return []
    header, body = rows[0], rows[1:]
    full = _table_to_markdown(rows)
    if len(full) <= max_chars or not body:
        return [_table_group_chunk(header, body, b)]
    # split body rows into header-prefixed groups under max_chars
    out: list[BlockChunk] = []
    group: list[list[str]] = []
    for row in body:
        group.append(row)
        if len(_table_to_markdown([header, *group])) > max_chars and len(group) > 1:
            group.pop()
            out.append(_table_group_chunk(header, group, b))
            group = [row]
    if group:
        out.append(_table_group_chunk(header, group, b))
    return out


def chunk_blocks(blocks: list[Block], *, max_chars: int = 1000) -> list[BlockChunk]:
    chunks: list[BlockChunk] = []
    buf: list[Block] = []
    buf_len = 0

    def flush() -> None:
        nonlocal buf, buf_len
        if not buf:
            return
        text = linearize_blocks(buf)
        if text.strip():
            chunks.append(BlockChunk(
                text=text, block_type=buf[0].type, section_path=buf[0].section_path,
            ))
        buf, buf_len = [], 0

    for b in blocks:
        if b.type == "table":
            flush()
            chunks.extend(_table_chunks(b, max_chars))
        elif b.type == "figure":
            flush()
            cap = b.caption or ""
            chunks.append(BlockChunk(
                text=f"[Figure: {cap}]" if cap else "[Figure]",
                block_type="figure", section_path=b.section_path,
                is_figure=True, caption=b.caption or None,
            ))
        elif b.type == "heading":
            flush()  # a heading starts a fresh chunk and binds following content
            buf, buf_len = [b], len(b.text)
        else:
            piece = b.text or ""
            if not piece:
                continue
            if len(piece) > max_chars:
                flush()
                for sub in _char_split(piece, max_chars):
                    chunks.append(BlockChunk(
                        text=sub, block_type=b.type, section_path=b.section_path,
                    ))
                continue
            if buf and buf_len + len(piece) > max_chars:
                flush()
            buf.append(b)
            buf_len += len(piece)
    flush()
    return chunks


def chunk_payload(c: BlockChunk) -> dict:
    """Qdrant per-chunk payload for a BlockChunk. Single source of truth for
    the structure-signal keys — imported by both embed paths so they never drift.
    """
    payload: dict = {
        "block_type": c.block_type,
        "is_table": c.is_table,
        "is_figure": c.is_figure,
        "section_path": c.section_path,
        "section_path_normalized": [s.lower() for s in c.section_path],
    }
    if c.caption:
        payload["caption"] = c.caption
    return payload
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/infrastructure/test_block_aware_chunker.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check infrastructure/text_chunkers/block_aware_chunker.py tests/infrastructure/test_block_aware_chunker.py
git add infrastructure/text_chunkers/block_aware_chunker.py tests/infrastructure/test_block_aware_chunker.py
git commit -m "feat(enrichment): block-aware chunker (Phase B)"
```

---

### Task B2: Per-chunk Qdrant payload + structure indexes

**Files:**
- Modify: `application/ports/vector_store.py` (port signature)
- Modify: `infrastructure/vector_stores/qdrant_store.py` (`upsert_page_chunk_embeddings`, `ensure_collection_exists`)
- Modify: `tests/mocks.py` (`MockVectorStore.upsert_page_chunk_embeddings` accepts `chunk_metadata`)
- Test: `tests/infrastructure/test_qdrant_chunk_metadata.py` *(new)*

**Interfaces:**
- Produces: `upsert_page_chunk_embeddings(..., chunk_metadata: list[dict] | None = None)` — when given, `chunk_metadata[i]` is merged into chunk *i*'s payload on top of the shared `metadata`. New payload indexes: `block_type` (keyword), `section_path_normalized` (keyword), `is_table` (bool), `is_figure` (bool). Consumed by Tasks B3, B4, B5.

- [ ] **Step 1: Write the failing test** — create `tests/infrastructure/test_qdrant_chunk_metadata.py`. This test exercises the payload-building logic by capturing points via a fake client:

```python
import pytest

from infrastructure.vector_stores.qdrant_store import QdrantStore
from tests.mocks import make_embedding


class _FakeClient:
    def __init__(self): self.upserts = []
    async def upsert(self, collection_name, points): self.upserts.append(points)
    async def delete(self, collection_name, points_selector): pass


@pytest.mark.asyncio
async def test_chunk_metadata_merges_per_chunk(monkeypatch):
    store = QdrantStore(collection_name="test")
    fake = _FakeClient()

    async def _get_client(): return fake
    monkeypatch.setattr(store, "_get_client", _get_client)

    from uuid import uuid4
    page_id, artifact_id = uuid4(), uuid4()
    embs = [make_embedding(), make_embedding()]
    await store.upsert_page_chunk_embeddings(
        page_id=page_id, artifact_id=artifact_id, embeddings=embs,
        page_index=0, chunk_count=2,
        metadata={"workspace_id": "ws"},
        chunk_metadata=[
            {"block_type": "table", "is_table": True, "is_figure": False},
            {"block_type": "paragraph", "is_table": False, "is_figure": False},
        ],
    )
    points = fake.upserts[0]
    assert points[0].payload["block_type"] == "table"
    assert points[0].payload["is_table"] is True
    assert points[0].payload["workspace_id"] == "ws"     # shared metadata still applied
    assert points[1].payload["block_type"] == "paragraph"
    assert points[1].payload["is_table"] is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/infrastructure/test_qdrant_chunk_metadata.py -v`
Expected: FAIL — `upsert_page_chunk_embeddings() got an unexpected keyword argument 'chunk_metadata'`.

- [ ] **Step 3: Implement.**

In `application/ports/vector_store.py`, update the `upsert_page_chunk_embeddings` signature in the `VectorStore` Protocol to add (after `sparse_embeddings`):

```python
        chunk_metadata: list[dict] | None = None,
```

In `infrastructure/vector_stores/qdrant_store.py`:

(a) `upsert_page_chunk_embeddings` — add the param and merge per chunk. Change the signature to add `chunk_metadata: list[dict] | None = None,` after `sparse_embeddings`, and inside the `for chunk_index, embedding in enumerate(embeddings):` loop, after `if metadata: payload.update(metadata)`:

```python
            if chunk_metadata and chunk_index < len(chunk_metadata):
                payload.update(chunk_metadata[chunk_index])
```

(b) `ensure_collection_exists` — extend the index list:

```python
            for field, schema in [
                ("artifact_id", models.PayloadSchemaType.KEYWORD),
                ("page_id", models.PayloadSchemaType.KEYWORD),
                ("workspace_id", models.PayloadSchemaType.KEYWORD),
                ("tag_normalized", models.PayloadSchemaType.KEYWORD),
                ("artifact_tag_normalized", models.PayloadSchemaType.KEYWORD),
                ("entity_types", models.PayloadSchemaType.KEYWORD),
                ("block_type", models.PayloadSchemaType.KEYWORD),
                ("section_path_normalized", models.PayloadSchemaType.KEYWORD),
                ("is_table", models.PayloadSchemaType.BOOL),
                ("is_figure", models.PayloadSchemaType.BOOL),
            ]:
```

In `tests/mocks.py`, update `MockVectorStore.upsert_page_chunk_embeddings` to accept and record `chunk_metadata`:

```python
    async def upsert_page_chunk_embeddings(
        self,
        page_id: UUID,
        artifact_id: UUID,
        embeddings: list[TextEmbedding],
        page_index: int,
        chunk_count: int,
        metadata: dict | None = None,
        sparse_embeddings: list | None = None,
        chunk_metadata: list[dict] | None = None,
    ) -> None:
        self.upsert_chunk_calls.append(
            {
                "page_id": page_id,
                "embeddings": embeddings,
                "chunk_count": chunk_count,
                "chunk_metadata": chunk_metadata,
            },
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/infrastructure/test_qdrant_chunk_metadata.py tests/application/test_embedding_use_cases.py -v`
Expected: PASS (new test + existing embedding tests unaffected — `chunk_metadata` defaults to None).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check application/ports/vector_store.py infrastructure/vector_stores/qdrant_store.py tests/mocks.py tests/infrastructure/test_qdrant_chunk_metadata.py
git add application/ports/vector_store.py infrastructure/vector_stores/qdrant_store.py tests/mocks.py tests/infrastructure/test_qdrant_chunk_metadata.py
git commit -m "feat(enrichment): per-chunk Qdrant payload + structure indexes (Phase B)"
```

---

### Task B3: `GeneratePageEmbeddingUseCase` reads IR + block-aware chunking

**Files:**
- Modify: `application/use_cases/embedding_use_cases.py` (`GeneratePageEmbeddingUseCase`)
- Modify: `infrastructure/di/container.py` (inject `blob_store`)
- Test: `tests/application/test_embedding_use_cases.py`

**Interfaces:**
- Consumes: `chunk_blocks`/`BlockChunk` (B1), `chunk_metadata` upsert param (B2), `ParsedDocument` (A1), `BlobStore`.
- Produces: `GeneratePageEmbeddingUseCase.__init__(..., blob_store: BlobStore | None = None)` (trailing optional — positional callers unaffected). When the IR blob exists and the page has blocks → block-aware chunks + per-chunk metadata. Else → unchanged char-chunk fallback. Helper `_load_page_blocks(artifact_id, page_index) -> list[Block] | None`.

- [ ] **Step 1: Write the failing tests** — append to `tests/application/test_embedding_use_cases.py`:

```python
import io
from uuid import uuid4

from application.dtos.parsed_document import Block, ParsedDocument


class _IRBlobStore:
    """Blob store exposing only one IR doc for a given artifact."""
    def __init__(self, artifact_id, blocks):
        self._key = f"artifacts/{artifact_id}/parsed/document.json"
        self._doc = ParsedDocument(source_mime="application/pdf", blocks=blocks)

    def exists(self, key): return key == self._key
    def get_bytes(self, key):
        if key != self._key:
            raise KeyError(key)
        return self._doc.model_dump_json().encode()


class TestGeneratePageEmbeddingBlockAware:
    @pytest.mark.asyncio
    async def test_uses_block_chunks_and_metadata_when_ir_present(self):
        page = _page_with_text("ignored — IR drives chunking")
        repo = MockPageRepository()
        repo.pages[page.id] = page
        blocks = [
            Block(type="heading", text="Results", level=1, section_path=[],
                  source_page_index=page.index),
            Block(type="table", rows=[["Cmpd", "IC50"], ["X", "5 nM"]],
                  caption="Table 1", section_path=["Results"], source_page_index=page.index),
        ]
        blob = _IRBlobStore(page.artifact_id, blocks)

        use_case = GeneratePageEmbeddingUseCase(
            repo, MockEmbeddingGenerator(), MockVectorStore(), MockTextChunker(),
            blob_store=blob,
        )
        # capture the upsert
        vs = use_case.vector_store
        result = await use_case.execute(page.id)
        assert isinstance(result, Success)
        call = vs.upsert_chunk_calls[-1]
        cm = call["chunk_metadata"]
        assert cm is not None
        # the table chunk carries is_table + section_path
        assert any(m["is_table"] for m in cm)
        assert any(m.get("section_path") == ["Results"] for m in cm)

    @pytest.mark.asyncio
    async def test_falls_back_to_char_chunker_when_no_ir(self):
        page = _page_with_text("A" * 200)
        repo = MockPageRepository()
        repo.pages[page.id] = page
        chunker = MockTextChunker(num_chunks=2)

        use_case = GeneratePageEmbeddingUseCase(
            repo, MockEmbeddingGenerator(), MockVectorStore(), chunker,
            blob_store=None,  # no IR
        )
        result = await use_case.execute(page.id)
        assert isinstance(result, Success)
        assert len(chunker.chunk_calls) == 1            # char chunker WAS used
        assert use_case.vector_store.upsert_chunk_calls[-1]["chunk_metadata"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/application/test_embedding_use_cases.py -k BlockAware -v`
Expected: FAIL — `__init__() got an unexpected keyword argument 'blob_store'`.

- [ ] **Step 3: Implement** in `application/use_cases/embedding_use_cases.py`.

Add imports at top:

```python
from application.dtos.parsed_document import Block, ParsedDocument
from infrastructure.text_chunkers.block_aware_chunker import chunk_blocks, chunk_payload
```

Add `blob_store` to `__init__` (trailing optional) and store it:

```python
    def __init__(
        self,
        page_repository: PageRepository,
        embedding_generator: EmbeddingGenerator,
        vector_store: VectorStore,
        text_chunker: TextChunker,
        sparse_embedding_generator: SparseEmbeddingGenerator | None = None,
        artifact_repository: ArtifactRepository | None = None,
        blob_store: "BlobStore | None" = None,
    ) -> None:
        ...
        self.blob_store = blob_store
```

Add the import guard for the type at top with the other imports:

```python
from application.ports.blob_store import BlobStore
```

Add a loader method (the payload builder is `chunk_payload`, imported from the chunker):

```python
    def _load_page_blocks(self, artifact_id: UUID, page_index: int) -> list[Block] | None:
        if self.blob_store is None:
            return None
        key = f"artifacts/{artifact_id}/parsed/document.json"
        try:
            if not self.blob_store.exists(key):
                return None
            doc = ParsedDocument.model_validate_json(self.blob_store.get_bytes(key))
        except Exception:
            logger.warning("embedding.ir_read_failed", artifact_id=str(artifact_id))
            return None
        return [b for b in doc.blocks if b.source_page_index == page_index]
```

Replace the chunking section (current step "4. Chunk the page text") so block-aware is tried first:

```python
            # 4. Chunk — block-aware from the IR blob if available, else char fallback.
            from infrastructure.config import settings as _settings

            page_blocks = self._load_page_blocks(page.artifact_id, page.index)
            chunk_metadata: list[dict] | None = None
            if page_blocks:
                block_chunks = [
                    bc for bc in chunk_blocks(page_blocks, max_chars=_settings.chunk_size)
                    if bc.text.strip()
                ]
                raw_chunk_texts = [bc.text for bc in block_chunks]
                chunk_metadata = [chunk_payload(bc) for bc in block_chunks]
                num_chunks = len(raw_chunk_texts)
            else:
                chunks = self.text_chunker.chunk_text(page.text_mention.text)
                raw_chunk_texts = [chunk.text for chunk in chunks]
                num_chunks = len(chunks)

            if not raw_chunk_texts:
                # block-aware produced nothing usable → char fallback
                chunks = self.text_chunker.chunk_text(page.text_mention.text)
                raw_chunk_texts = [chunk.text for chunk in chunks]
                chunk_metadata = None
                num_chunks = len(chunks)

            logger.info(
                "text_chunked",
                page_id=str(page_id),
                num_chunks=num_chunks,
                block_aware=chunk_metadata is not None,
                text_length=len(page.text_mention.text),
            )
```

Then everywhere downstream that used `len(chunks)` use `num_chunks`, and pass `chunk_metadata` to the upsert. Specifically update the upsert call:

```python
            await self.vector_store.upsert_page_chunk_embeddings(
                page_id=page_id,
                artifact_id=page.artifact_id,
                embeddings=embeddings,
                page_index=page.index,
                chunk_count=num_chunks,
                metadata=upsert_metadata or None,
                sparse_embeddings=sparse_embeddings,
                chunk_metadata=chunk_metadata,
            )
```

And the success-log `chunk_count=len(chunks)` → `chunk_count=num_chunks`.

> Note: `BlobStore` is imported at module top (not under TYPE_CHECKING) because it's referenced as a runtime default-None annotation in a string — keeping it a real import avoids a forward-ref headache and the module already imports many ports directly.

Wire DI — in `infrastructure/di/container.py`, the `GeneratePageEmbeddingUseCase` lambda gains `blob_store=c[BlobStore]`:

```python
    container[GeneratePageEmbeddingUseCase] = lambda c: GeneratePageEmbeddingUseCase(
        page_repository=c[PageRepository],
        embedding_generator=c[EmbeddingGenerator],
        vector_store=c[VectorStore],
        text_chunker=c[TextChunker],
        sparse_embedding_generator=c[SparseEmbeddingGenerator],
        artifact_repository=c[ArtifactRepository],
        blob_store=c[BlobStore],
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/application/test_embedding_use_cases.py -v`
Expected: PASS (new block-aware tests + all existing).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check application/use_cases/embedding_use_cases.py infrastructure/di/container.py tests/application/test_embedding_use_cases.py
git add application/use_cases/embedding_use_cases.py infrastructure/di/container.py tests/application/test_embedding_use_cases.py
git commit -m "feat(enrichment): page embedding reads IR + block-aware chunking (Phase B)"
```

---

### Task B4: `BatchReEmbedArtifactPagesUseCase` reads IR + block-aware chunking

**Files:**
- Modify: `application/use_cases/batch_reembed_use_cases.py` (`BatchReEmbedArtifactPagesUseCase`)
- Modify: `infrastructure/di/container.py` (inject `blob_store`)
- Test: `tests/application/test_batch_reembed_use_cases.py` *(new, or append if exists)*

**Interfaces:**
- Consumes: `chunk_blocks`/`BlockChunk` (B1), `chunk_metadata` upsert (B2), `BlobStore`.
- Produces: `BatchReEmbedArtifactPagesUseCase.__init__(..., blob_store: BlobStore | None = None)`. `_process_page_batch` chunks block-aware when the artifact's IR blob is present, carrying per-chunk metadata into the upsert; char fallback otherwise. The IR doc is loaded **once per artifact** (not per page).

- [ ] **Step 1: Write the failing test** — create `tests/application/test_batch_reembed_use_cases.py`:

```python
import pytest
from uuid import uuid4

from application.dtos.parsed_document import Block, ParsedDocument
from application.use_cases.batch_reembed_use_cases import BatchReEmbedArtifactPagesUseCase
from domain.aggregates.page import Page
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
    from domain.aggregates.artifact import Artifact
    from domain.value_objects.artifact_type import ArtifactType
    from domain.value_objects.mime_type import MimeType
    artifact = Artifact.create(
        artifact_type=ArtifactType.RESEARCH_ARTICLE, mime_type=MimeType.PDF,
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
```

> If `Artifact.create` / `Page.create` signatures differ, mirror the construction already used in `tests/application/test_embedding_use_cases.py` and `test_parse_artifact_use_case.py`. The load-bearing assertions are the last three lines.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/application/test_batch_reembed_use_cases.py -v`
Expected: FAIL — `__init__() got an unexpected keyword argument 'blob_store'`.

- [ ] **Step 3: Implement** in `application/use_cases/batch_reembed_use_cases.py`.

Add to `TYPE_CHECKING` imports: `from application.ports.blob_store import BlobStore`. Add runtime imports near the top of the module (outside TYPE_CHECKING, since used at call time):

```python
from application.dtos.parsed_document import Block, ParsedDocument
from infrastructure.text_chunkers.block_aware_chunker import chunk_blocks, chunk_payload
```

Add `blob_store` to `__init__` (trailing optional) and store it:

```python
        blob_store: BlobStore | None = None,
        ...
        self.blob_store = blob_store
```

Add a loader (the payload builder is `chunk_payload`, imported from the chunker — identical shape to B3):

```python
    def _load_ir_blocks(self, artifact_id: UUID) -> dict[int, list[Block]] | None:
        """Load the artifact IR once, grouped by page index. None if absent."""
        if self.blob_store is None:
            return None
        key = f"artifacts/{artifact_id}/parsed/document.json"
        try:
            if not self.blob_store.exists(key):
                return None
            doc = ParsedDocument.model_validate_json(self.blob_store.get_bytes(key))
        except Exception:
            logger.warning("batch_reembed.ir_read_failed", artifact_id=str(artifact_id))
            return None
        by_page: dict[int, list[Block]] = {}
        for b in doc.blocks:
            if b.source_page_index is not None:
                by_page.setdefault(b.source_page_index, []).append(b)
        return by_page
```

In `execute`, load the IR once and thread it into `_process_page_batch`:

```python
        ir_by_page = self._load_ir_blocks(artifact_id)
        ...
            pages_processed, chunks_processed = await self._process_page_batch(
                batch_page_ids, artifact_title, artifact_id, ir_by_page,
            )
```

Update `_process_page_batch` signature to accept `ir_by_page: dict[int, list[Block]] | None` and build per-page chunk metadata. Replace the per-page chunking block:

```python
        page_chunk_groups: list[tuple[Page, int, list[dict] | None]] = []
        all_contextual_texts: list[str] = []

        for page_id in page_ids:
            page = self.page_repository.get_by_id(page_id)
            if not page.text_mention or not page.text_mention.text:
                continue

            page_blocks = (ir_by_page or {}).get(page.index)
            chunk_metadata: list[dict] | None = None
            if page_blocks:
                from infrastructure.config import settings as _settings
                bchunks = [
                    bc for bc in chunk_blocks(page_blocks, max_chars=_settings.chunk_size)
                    if bc.text.strip()
                ]
                if bchunks:
                    raw_texts = [bc.text for bc in bchunks]
                    chunk_metadata = [chunk_payload(bc) for bc in bchunks]
                else:
                    raw_texts = [c.text for c in self.text_chunker.chunk_text(page.text_mention.text)]
            else:
                raw_texts = [c.text for c in self.text_chunker.chunk_text(page.text_mention.text)]

            from infrastructure.config import settings as _settings
            context_prefix = (
                self._build_chunk_context(artifact_title, page)
                if _settings.embedding_enable_context_enrichment
                else ""
            )
            for t in raw_texts:
                all_contextual_texts.append(context_prefix + t)

            page_chunk_groups.append((page, len(raw_texts), chunk_metadata))
```

Update the embedding-distribution loop to use the new tuple shape and pass `chunk_metadata`:

```python
        embedding_offset = 0
        for page, page_embedding_count, chunk_metadata in page_chunk_groups:
            page_embeddings = embeddings[embedding_offset : embedding_offset + page_embedding_count]
            embedding_offset += page_embedding_count

            metadata = self._build_page_metadata(page)

            await self.vector_store.upsert_page_chunk_embeddings(
                page_id=page.id,
                artifact_id=artifact_id,
                embeddings=page_embeddings,
                page_index=page.index,
                chunk_count=page_embedding_count,
                metadata=metadata or None,
                sparse_embeddings=None,
                chunk_metadata=chunk_metadata,
            )

        return len(page_chunk_groups), len(all_contextual_texts)
```

Wire DI — in `infrastructure/di/container.py`, add `blob_store=c[BlobStore]` to the `BatchReEmbedArtifactPagesUseCase` lambda.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/application/test_batch_reembed_use_cases.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check application/use_cases/batch_reembed_use_cases.py infrastructure/di/container.py tests/application/test_batch_reembed_use_cases.py
git add application/use_cases/batch_reembed_use_cases.py infrastructure/di/container.py tests/application/test_batch_reembed_use_cases.py
git commit -m "feat(enrichment): batch re-embed reads IR + block-aware chunking (Phase B)"
```

---

### Task B5: Structure-aware search filters

**Files:**
- Modify: `application/dtos/embedding_dtos.py` (`SearchRequest`)
- Modify: `infrastructure/vector_stores/qdrant_store.py` (`_build_filter`, `search_pages_grouped`, `search_hybrid_grouped`)
- Modify: `application/ports/vector_store.py` (port signatures for the two grouped searches)
- Modify: `application/use_cases/embedding_use_cases.py` (`SearchSimilarPagesUseCase.execute` filter_kwargs)
- Test: `tests/infrastructure/test_qdrant_filters.py` *(new)*

**Interfaces:**
- Produces: `SearchRequest.block_types: list[str] | None`, `SearchRequest.section: str | None`, `SearchRequest.is_table: bool | None`, `SearchRequest.is_figure: bool | None`. `_build_filter(..., block_types=None, section=None, is_table=None, is_figure=None)` adds matching conditions (`block_type` MatchAny; `section_path_normalized` MatchValue lowercased; `is_table`/`is_figure` MatchValue bool). Threaded through `search_pages_grouped` + `search_hybrid_grouped` + the port.

- [ ] **Step 1: Write the failing test** — create `tests/infrastructure/test_qdrant_filters.py`:

```python
from uuid import uuid4

from qdrant_client import models

from infrastructure.vector_stores.qdrant_store import QdrantStore


def _keys(flt: models.Filter) -> list[str]:
    out = []
    for cond in (flt.must or []):
        if isinstance(cond, models.FieldCondition):
            out.append(cond.key)
        elif isinstance(cond, models.Filter):
            for sub in (cond.should or []):
                if isinstance(sub, models.FieldCondition):
                    out.append(sub.key)
    return out


def test_build_filter_includes_structure_conditions():
    store = QdrantStore(collection_name="t")
    flt = store._build_filter(
        block_types=["table"], section="Methods", is_table=True, is_figure=None,
    )
    keys = _keys(flt)
    assert "block_type" in keys
    assert "section_path_normalized" in keys
    assert "is_table" in keys
    assert "is_figure" not in keys  # None → omitted


def test_build_filter_none_when_empty():
    store = QdrantStore(collection_name="t")
    assert store._build_filter() is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/infrastructure/test_qdrant_filters.py -v`
Expected: FAIL — `_build_filter() got an unexpected keyword argument 'block_types'`.

- [ ] **Step 3: Implement.**

In `application/dtos/embedding_dtos.py`, add to `SearchRequest` (after `tag_match_mode`):

```python
    block_types: list[str] | None = Field(
        default=None,
        description="Filter by block type (e.g. 'table', 'figure', 'heading', 'paragraph').",
    )
    section: str | None = Field(
        default=None,
        description="Filter to chunks under a heading whose text matches (case-insensitive).",
    )
    is_table: bool | None = Field(
        default=None, description="If set, restrict to table (True) or non-table (False) chunks.",
    )
    is_figure: bool | None = Field(
        default=None, description="If set, restrict to figure (True) or non-figure (False) chunks.",
    )
```

In `infrastructure/vector_stores/qdrant_store.py`, extend `_build_filter` to accept and apply the new params. Add to the signature (after `tag_match_mode`):

```python
        block_types: list[str] | None = None,
        section: str | None = None,
        is_table: bool | None = None,
        is_figure: bool | None = None,
```

and before the final `return`:

```python
        if block_types:
            must_conditions.append(
                models.FieldCondition(
                    key="block_type", match=models.MatchAny(any=block_types),
                ),
            )
        if section:
            must_conditions.append(
                models.FieldCondition(
                    key="section_path_normalized",
                    match=models.MatchValue(value=section.lower()),
                ),
            )
        if is_table is not None:
            must_conditions.append(
                models.FieldCondition(key="is_table", match=models.MatchValue(value=is_table)),
            )
        if is_figure is not None:
            must_conditions.append(
                models.FieldCondition(key="is_figure", match=models.MatchValue(value=is_figure)),
            )
```

Thread the four params through `search_pages_grouped` and `search_hybrid_grouped` — add them to each signature (after `tag_match_mode`) and pass them into the `self._build_filter(...)` call in each. Mirror the existing keyword passing style. Add the same four params to the corresponding methods in the `VectorStore` Protocol (`application/ports/vector_store.py`).

In `application/use_cases/embedding_use_cases.py`, `SearchSimilarPagesUseCase.execute`, extend `filter_kwargs`:

```python
            filter_kwargs = dict(
                artifact_id_filter=request.artifact_id,
                score_threshold=request.score_threshold,
                allowed_artifact_ids=allowed_artifact_ids,
                workspace_id=workspace_id,
                tags=request.tags,
                entity_types=request.entity_types,
                tag_match_mode=request.tag_match_mode,
                block_types=request.block_types,
                section=request.section,
                is_table=request.is_table,
                is_figure=request.is_figure,
            )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/infrastructure/test_qdrant_filters.py tests/application/test_embedding_use_cases.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check application/dtos/embedding_dtos.py infrastructure/vector_stores/qdrant_store.py application/ports/vector_store.py application/use_cases/embedding_use_cases.py tests/infrastructure/test_qdrant_filters.py
git add application/dtos/embedding_dtos.py infrastructure/vector_stores/qdrant_store.py application/ports/vector_store.py application/use_cases/embedding_use_cases.py tests/infrastructure/test_qdrant_filters.py
git commit -m "feat(enrichment): structure-aware search filters (Phase B)"
```

---

### Task B6: Reranker sees section_path + caption

**Files:**
- Modify: `application/use_cases/embedding_use_cases.py` (`SearchSimilarPagesUseCase` rerank-doc construction)
- Test: `tests/application/test_embedding_use_cases.py`

**Interfaces:**
- Consumes: `result.metadata` (the chunk payload returned on `PageSearchResult` from grouped search, carrying `section_path` + `caption` from B3/B4).
- Produces: the reranker document text is prefixed with `section_path` breadcrumb + `caption` when present, improving cross-encoder precision. Pure string-building change; no signature change.

- [ ] **Step 1: Write the failing test** — append to `tests/application/test_embedding_use_cases.py`. This unit-tests a small extracted helper so we don't need a live reranker:

```python
class TestRerankDocText:
    def test_prefixes_section_and_caption(self):
        from application.use_cases.embedding_use_cases import _rerank_doc_text
        text = _rerank_doc_text(
            page_text="IC50 was 2 nM.",
            metadata={"section_path": ["Results", "Assay"], "caption": "Table 1: potency"},
        )
        assert "Results > Assay" in text
        assert "Table 1: potency" in text
        assert "IC50 was 2 nM." in text

    def test_plain_text_when_no_metadata(self):
        from application.use_cases.embedding_use_cases import _rerank_doc_text
        assert _rerank_doc_text("body", None) == "body"
        assert _rerank_doc_text("body", {}) == "body"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/application/test_embedding_use_cases.py -k RerankDocText -v`
Expected: FAIL — `cannot import name '_rerank_doc_text'`.

- [ ] **Step 3: Implement** in `application/use_cases/embedding_use_cases.py`.

Add a module-level helper (above the use-case classes):

```python
def _rerank_doc_text(page_text: str, metadata: dict | None) -> str:
    """Prepend section breadcrumb + caption (if any) to the reranker document."""
    prefix_parts: list[str] = []
    if metadata:
        section_path = metadata.get("section_path")
        if section_path:
            prefix_parts.append(" > ".join(section_path))
        caption = metadata.get("caption")
        if caption:
            prefix_parts.append(caption)
    if not prefix_parts:
        return page_text
    return " | ".join(prefix_parts) + "\n\n" + page_text
```

In the rerank loop inside `SearchSimilarPagesUseCase.execute`, replace the `rerank_docs` text construction:

```python
                for r in search_results:
                    page = await self.page_read_model.get_page_by_id(r.page_id)
                    text = ""
                    if page and page.text_mention and page.text_mention.text:
                        text = page.text_mention.text[:2000]
                    if not text.strip():
                        continue  # skip empty pages — cross-encoder returns nan for empty text
                    doc_text = _rerank_doc_text(text, r.metadata)
                    rerank_docs.append(RerankDocument(id=str(r.page_id), text=doc_text))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/application/test_embedding_use_cases.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check application/use_cases/embedding_use_cases.py tests/application/test_embedding_use_cases.py
git add application/use_cases/embedding_use_cases.py tests/application/test_embedding_use_cases.py
git commit -m "feat(enrichment): reranker sees section_path + caption (Phase B)"
```

---

## Final verification (after B6)

- [ ] **Full suite green:** `uv run pytest -q` — expect the prior baseline (485+) plus the new tests, all passing.
- [ ] **Lint clean:** `uv run ruff check .` (or the project `make lint`).
- [ ] **Boot check (DI wiring):** `uv run python -c "from infrastructure.di.container import build_container; build_container()"` — must not raise (confirms `blob_store=c[BlobStore]` resolves for both embedding use cases). If `build_container` has a different name/signature, use the project's existing container-boot entrypoint.
- [ ] Update `.superpowers/sdd/progress.md` with the Phase A+B range and any deferred minors.

## Out of scope (follow-on plans, per spec §6)

- **Phase C** — first-class figure crops (capture via `get_image`, `GET /artifacts/{id}/figures/{n}`, multimodal chat), optional figure→VLM→NER hop.
- **Phase D** — structured tables in chat (`ContentBlockDTO`/`structured_block`), block-level citations.
- **Backfill ops** — re-parse + re-embed of the existing corpus to gain Phase A/B benefits (the async parse workflow is idempotent; batch re-embed exists). Bound by Temporal concurrency; run per-phase after the retrieval-quality check (§8).

---

## Self-Review

**Spec coverage (Phases A+B):**
- §5A populate `level`/`caption`/`section_path` → A1 (field + algorithm) + A2 (parser). `linearize_blocks` already renders them (verified) → A1 guard test. ✓
- §5A NER yield boost → automatic via existing `Page.TextMentionUpdated` path; no code (Global Constraint §3). ✓
- §5B block-aware chunking (table intact, heading bound, size cap, row-split, char-split) → B1. ✓
- §5B per-chunk payload (`block_type`/`section_path`/`is_table`/`is_figure`/`caption`) + indexes → B2. ✓
- §5B read IR blob at embed time + char fallback when absent → B3 (page) + B4 (batch). ✓
- §5B search filters (`block_types`/`section`/`is_table`/`is_figure`) → B5. ✓
- §5B reranker doc includes section/caption → B6. ✓
- §4 zero new aggregate events / read-model churn → only Qdrant payload + IR reads; verified no event/Mongo touch. ✓
- §3 CSER untouched, never fed crops; NER fed via captions-in-text → no CSER/NER code. ✓

**Type consistency:** `BlockChunk` fields and the `chunk_payload` keys (`block_type`/`is_table`/`is_figure`/`section_path`/`section_path_normalized`/`caption`) live in **one** place (B1, `block_aware_chunker.py`) and are imported by B3+B4 — no drift possible. `chunk_metadata` param name and `_build_filter` keys match B2→B5. `num_chunks` replaces `len(chunks)` consistently in B3.

**Deferred/known ceilings (marked in code):** naive char-split for a single oversized block (`ponytail:` comment, B1); `section` filter matches a single heading string against the normalized path list (multi-segment section queries not supported — YAGNI until needed).
