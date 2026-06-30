# Phase D — Per-Table Entity Grounding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tag each table chunk with the entities the table is actually about (scoped from its own caption/section/headers/cells) instead of the page-wide NER union, so a target-specific query stops matching an unrelated table (e.g. a Rho query no longer surfaces a PptT table).

**Architecture:** One pure helper (`scope_table_entities`) attributes the page's already-extracted NER entities to a table by word-boundary presence in the table's local text. The two embed paths call it for `is_table` chunks and merge the scoped tags into Phase B's per-chunk `chunk_metadata`, which already overrides the shared page-union at Qdrant upsert. Ingestion-only; no retrieval, model, DTO, schema, or DI changes.

**Tech Stack:** Python 3.12, Pydantic v2, Qdrant, pytest, `uv`. Spec: `design_docs/DOCLING_PHASE_D_TABLE_GROUNDING.md`.

## Global Constraints

- **Run every Python command with `uv run`.** Working dir: `/Users/sidx/workspace/docu-store/services`.
- **Lint clean before each commit:** `uv run ruff check <changed source files under application/ infrastructure/>` (the project lint gate covers `application/ domain/ infrastructure/ interfaces/`, not `tests/` or `scripts/`).
- **No retrieval/query changes** — `query_planning.py`, search use cases, filters, rerank untouched.
- **No new models / LLM / extra NER passes / new aggregate events / read-model fields.** Reuse page-level NER output; signals live in the Qdrant chunk payload.
- **Tables only** (`is_table` chunks). Prose/heading chunks keep today's page-union behavior.
- **Precision over recall:** no local entity match → empty table-level tags, never the page union.
- **Word-boundary matching, not substring** (`rho` must not match `rhodamine`).

---

## Task 1: `scope_table_entities` helper (pure)

**Files:**
- Modify: `infrastructure/text_chunkers/block_aware_chunker.py` (add `import re`; append `scope_table_entities`)
- Test: `tests/infrastructure/test_block_aware_chunker.py` (append tests)

**Interfaces:**
- Produces: `scope_table_entities(candidates: list[tuple[str, str | None]], local_text: str) -> dict` returning `{"tags": list[str], "tag_normalized": list[str], "entity_types": list[str]}`. Keeps a candidate iff `tag.lower()` occurs in `local_text.lower()` on a word boundary. Empty lists when nothing matches. Consumed by Tasks 2 and 3.

- [ ] **Step 1: Write the failing tests** — append to `tests/infrastructure/test_block_aware_chunker.py`:

```python
from infrastructure.text_chunkers.block_aware_chunker import scope_table_entities


def test_scope_keeps_local_entity_drops_remote():
    candidates = [("PptT", "target"), ("Rho", "target"), ("CmpdX", "compound_name")]
    local = "| Cmpd | IC50 |\n| CmpdX | 5 nM |\n\n*Table 1. PptT inhibition*"
    out = scope_table_entities(candidates, local)
    assert out["tag_normalized"] == ["pptt", "cmpdx"]   # PptT (caption) + CmpdX (cell)
    assert "rho" not in out["tag_normalized"]            # Rho not in the table's own text
    assert out["entity_types"] == ["compound_name", "target"]


def test_scope_word_boundary_not_substring():
    out = scope_table_entities([("Rho", "target")], "rhodamine staining only")
    assert out["tag_normalized"] == []                   # 'rho' must not match 'rhodamine'


def test_scope_section_heading_contributes():
    # local_text = table markdown + " " + " ".join(section_path)
    local = "| Cmpd | IC50 |\n| CmpdX | 5 nM | Rho inhibitors"
    out = scope_table_entities([("Rho", "target")], local)
    assert out["tag_normalized"] == ["rho"]


def test_scope_empty_when_no_local_match():
    out = scope_table_entities(
        [("PptT", "target"), ("Rho", "target")],
        "| Cmpd | IC50 |\n| CmpdX | 5 nM |",
    )
    assert out == {"tags": [], "tag_normalized": [], "entity_types": []}


def test_scope_ignores_blank_candidate():
    out = scope_table_entities([("", "target")], "anything here")
    assert out["tag_normalized"] == []                   # blank tag never matches
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/infrastructure/test_block_aware_chunker.py -k scope -v`
Expected: FAIL — `ImportError: cannot import name 'scope_table_entities'`.

- [ ] **Step 3a: Add the `re` import** — edit `infrastructure/text_chunkers/block_aware_chunker.py`. Replace:

```python
from __future__ import annotations

from dataclasses import dataclass, field
```

with:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
```

- [ ] **Step 3b: Append the helper** at the end of `infrastructure/text_chunkers/block_aware_chunker.py`:

```python
def scope_table_entities(
    candidates: list[tuple[str, str | None]],
    local_text: str,
) -> dict:
    """Scope a table chunk's entity tags to entities that actually appear in the
    table's own local text (caption / section / headers / cells), instead of the
    page-wide NER union. A candidate is kept only if its surface form occurs in
    local_text on a word boundary (case-insensitive) — so 'rho' does not match
    'rhodamine'. Returns {tags, tag_normalized, entity_types}; empty lists when
    nothing matches (precision over recall: a wrong target tag pollutes chat, a
    missing one degrades to doc-level + vector match). Pure: no IO, no models.
    """
    low = local_text.lower()
    tags: list[str] = []
    tag_normalized: list[str] = []
    entity_types: set[str] = set()
    seen: set[str] = set()
    for tag, entity_type in candidates:
        norm = tag.lower()
        if not norm:
            continue
        if not re.search(r"\b" + re.escape(norm) + r"\b", low):
            continue
        if norm not in seen:
            seen.add(norm)
            tags.append(tag)
            tag_normalized.append(norm)
        if entity_type:
            entity_types.add(entity_type)
    return {
        "tags": tags,
        "tag_normalized": tag_normalized,
        "entity_types": sorted(entity_types),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/infrastructure/test_block_aware_chunker.py -v`
Expected: PASS (the 5 new tests + all existing chunker tests).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check infrastructure/text_chunkers/block_aware_chunker.py
git add infrastructure/text_chunkers/block_aware_chunker.py tests/infrastructure/test_block_aware_chunker.py
git commit -m "feat(enrichment): scope_table_entities helper (Phase D)"
```

---

## Task 2: `GeneratePageEmbeddingUseCase` scopes table chunk tags

**Files:**
- Modify: `application/use_cases/embedding_use_cases.py` (import + scoping block in the block-aware branch)
- Test: `tests/application/test_embedding_use_cases.py` (append to `TestGeneratePageEmbeddingBlockAware`)

**Interfaces:**
- Consumes: `scope_table_entities` (Task 1), the existing block-aware path (`block_chunks`, `chunk_metadata`, `page.tag_mentions`).
- Produces: table chunks in the upserted `chunk_metadata` carry table-scoped `tags`/`tag_normalized`/`entity_types`; prose chunks unchanged.

- [ ] **Step 1: Write the failing test** — in `tests/application/test_embedding_use_cases.py`, ensure the `TagMention` import is present at the top (add if missing):

```python
from domain.value_objects.tag_mention import TagMention
```

Then append this method inside the existing `class TestGeneratePageEmbeddingBlockAware:`:

```python
    @pytest.mark.asyncio
    async def test_table_chunk_tags_scoped_to_table_entities(self):
        page = _page_with_text("Rho is discussed in the intro; the PptT assay is below.")
        page.update_tag_mentions([
            TagMention(tag="PptT", entity_type="target"),
            TagMention(tag="Rho", entity_type="target"),
        ])
        repo = MockPageRepository()
        repo.pages[page.id] = page
        blocks = [
            Block(
                type="table",
                rows=[["Cmpd", "IC50"], ["X", "5 nM"]],
                caption="Table 1. PptT inhibition",
                section_path=["Results"],
                source_page_index=page.index,
            ),
        ]
        use_case = GeneratePageEmbeddingUseCase(
            repo,
            MockEmbeddingGenerator(),
            MockVectorStore(),
            MockTextChunker(),
            blob_store=_IRBlobStore(page.artifact_id, blocks),
        )
        vs = use_case.vector_store
        result = await use_case.execute(page.id)
        assert isinstance(result, Success)
        cm = vs.upsert_chunk_calls[-1]["chunk_metadata"]
        table_meta = next(m for m in cm if m.get("is_table"))
        assert table_meta["tag_normalized"] == ["pptt"]   # PptT in caption; Rho dropped
        assert "rho" not in table_meta["tag_normalized"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/application/test_embedding_use_cases.py -k test_table_chunk_tags_scoped -v`
Expected: FAIL — `KeyError: 'tag_normalized'` (the table chunk_metadata has no scoped tags yet).

- [ ] **Step 3a: Extend the import** in `application/use_cases/embedding_use_cases.py`. Replace:

```python
from infrastructure.text_chunkers.block_aware_chunker import chunk_blocks, chunk_payload
```

with:

```python
from infrastructure.text_chunkers.block_aware_chunker import (
    chunk_blocks,
    chunk_payload,
    scope_table_entities,
)
```

- [ ] **Step 3b: Add the scoping block.** In `GeneratePageEmbeddingUseCase.execute`, replace:

```python
                raw_chunk_texts = [bc.text for bc in block_chunks]
                chunk_metadata = [chunk_payload(bc) for bc in block_chunks]
                num_chunks = len(raw_chunk_texts)
```

with:

```python
                raw_chunk_texts = [bc.text for bc in block_chunks]
                chunk_metadata = [chunk_payload(bc) for bc in block_chunks]
                # Phase D: scope each TABLE chunk's tags to the entities in the
                # table's own text/caption/section, overriding the page-wide union
                # (upsert_metadata below) so a table isn't matched by an unrelated
                # target mentioned elsewhere on the page.
                if page.tag_mentions:
                    candidates = [(tm.tag, tm.entity_type) for tm in page.tag_mentions]
                    for idx, bc in enumerate(block_chunks):
                        if bc.is_table:
                            local = bc.text + " " + " ".join(bc.section_path)
                            chunk_metadata[idx].update(
                                scope_table_entities(candidates, local),
                            )
                num_chunks = len(raw_chunk_texts)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/application/test_embedding_use_cases.py -v`
Expected: PASS (new test + all existing embedding tests).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check application/use_cases/embedding_use_cases.py
git add application/use_cases/embedding_use_cases.py tests/application/test_embedding_use_cases.py
git commit -m "feat(enrichment): page embedding scopes table chunk tags (Phase D)"
```

---

## Task 3: `BatchReEmbedArtifactPagesUseCase` scopes table chunk tags

**Files:**
- Modify: `application/use_cases/batch_reembed_use_cases.py` (import + scoping block in `_process_page_batch`)
- Test: `tests/application/test_batch_reembed_use_cases.py` (append)

**Interfaces:**
- Consumes: `scope_table_entities` (Task 1), the existing block-aware path (`bchunks`, `chunk_metadata`, `page.tag_mentions`).
- Produces: identical scoping behavior to Task 2 in the batch re-embed path.

- [ ] **Step 1: Write the failing test** — add the import near the top of `tests/application/test_batch_reembed_use_cases.py`:

```python
from domain.value_objects.tag_mention import TagMention
```

Then append:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/application/test_batch_reembed_use_cases.py -k scopes_table_tags -v`
Expected: FAIL — `KeyError: 'tag_normalized'`.

- [ ] **Step 3a: Extend the import** in `application/use_cases/batch_reembed_use_cases.py`. Replace:

```python
from infrastructure.text_chunkers.block_aware_chunker import chunk_blocks, chunk_payload
```

with:

```python
from infrastructure.text_chunkers.block_aware_chunker import (
    chunk_blocks,
    chunk_payload,
    scope_table_entities,
)
```

- [ ] **Step 3b: Add the scoping block.** In `_process_page_batch`, replace:

```python
                if bchunks:
                    raw_texts = [bc.text for bc in bchunks]
                    chunk_metadata = [chunk_payload(bc) for bc in bchunks]
                else:
```

with:

```python
                if bchunks:
                    raw_texts = [bc.text for bc in bchunks]
                    chunk_metadata = [chunk_payload(bc) for bc in bchunks]
                    # Phase D: scope each TABLE chunk's tags to the entities in the
                    # table's own text/caption/section, overriding the page-wide
                    # union (_build_page_metadata) so a table isn't matched by an
                    # unrelated target mentioned elsewhere on the page.
                    if page.tag_mentions:
                        candidates = [(tm.tag, tm.entity_type) for tm in page.tag_mentions]
                        for idx, bc in enumerate(bchunks):
                            if bc.is_table:
                                local = bc.text + " " + " ".join(bc.section_path)
                                chunk_metadata[idx].update(
                                    scope_table_entities(candidates, local),
                                )
                else:
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/application/test_batch_reembed_use_cases.py -v`
Expected: PASS (new test + existing batch re-embed tests).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check application/use_cases/batch_reembed_use_cases.py
git add application/use_cases/batch_reembed_use_cases.py tests/application/test_batch_reembed_use_cases.py
git commit -m "feat(enrichment): batch re-embed scopes table chunk tags (Phase D)"
```

---

## Final verification (after Task 3)

- [ ] **Full suite green:** `uv run pytest -q` — expect the prior baseline (508) plus the new tests, all passing.
- [ ] **Lint clean:** `uv run ruff check application/ domain/ infrastructure/ interfaces/`.
- [ ] **Boot check (DI wiring unchanged):** `uv run python -c "from infrastructure.di.container import create_container; create_container()"` — must not raise.

---

## Self-Review

**Spec coverage (`DOCLING_PHASE_D_TABLE_GROUNDING.md`):**
- §3.1 pure attribution helper (word-boundary, empty-on-no-match) → Task 1. ✓
- §3.2 table-chunks-only scoping merged into `chunk_metadata`, overriding page-union → Tasks 2 + 3 (both embed paths). ✓
- §3.3 doc-subject + provenance already present → no work (verified `artifact_tag_normalized` + Phase B `section_path`/`caption` + retrieval-time author/title/date). ✓
- §3.4 precision over recall (empty tags on no match) → Task 1 helper returns empty lists; `test_scope_empty_when_no_local_match`. ✓
- §4 touchpoints (chunker + 2 use cases + tests; no port/DTO/schema/DI change) → Tasks 1–3 only. ✓
- §5 testing (PptT-kept/Rho-dropped, word-boundary, section heading, empty; embed-path table-vs-union) → Task 1 unit tests + Task 2/3 embed-path tests. ✓

**Placeholder scan:** none — every step shows exact code/commands.

**Type consistency:** `scope_table_entities(candidates: list[tuple[str, str | None]], local_text: str) -> dict` defined in Task 1 is called identically in Tasks 2 and 3 with `candidates = [(tm.tag, tm.entity_type) for tm in page.tag_mentions]` and `local = bc.text + " " + " ".join(bc.section_path)`. Returned dict keys (`tags`/`tag_normalized`/`entity_types`) match the `chunk_metadata[idx].update(...)` merge and the test assertions.
