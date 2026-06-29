# Multi-Format Ingestion — Phase 0 + 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move PDF ingestion off the synchronous parse-in-the-request saga onto a durable, async, Docling-based parsing workflow that produces a structured `ParsedDocument` and the same `Page.Created` / `Page.TextMentionUpdated` events the existing pipeline already consumes — with no change to downstream extraction.

**Architecture:** A thin upload saga stores the blob + creates the `Artifact`; `Artifact.Created` triggers a `ParseArtifactWorkflow` (rebuilt from the dead `ProcessArtifactWorkflow`); a `parse_artifact` activity runs `ParseArtifactUseCase`, which parses via Docling into a neutral `ParsedDocument` IR (stored as a blob), segments it (one `Page` per physical page for PDF), and creates pages with deterministic IDs (retry-safe). Built alongside the old path in Phase 0; cut over atomically in Phase 1.

**Tech Stack:** Python 3.12+, FastAPI, Temporal (`temporalio`), `eventsourcing`, `returns` (Result), `lagom` (DI), Pydantic v2, Qdrant, MongoDB, `pytest` + `pytest-asyncio`, **Docling** (new), PyMuPDF (retained — for CSER + metadata, not for upload parsing).

## Global Constraints

- **Run all Python via `uv run`** (e.g. `uv run pytest ...`). Add deps via `uv add`.
- **Result pattern:** use cases return `returns.result.Result[T, AppError]` and use the `@handle_domain_errors` decorator (see existing use cases).
- **DI is `lagom`:** register with `container[T] = lambda c: T(dep=c[Dep], ...)` in `infrastructure/di/container.py`.
- **Aggregates are `eventsourcing`:** IDs auto-generate unless created via `_create(..., id=...)`.
- **Do NOT rename `Page` or any event** (`Page.Created`, `Page.TextMentionUpdated`, etc.) — zero event-store migration.
- **Image blob keys are unchanged:** `artifacts/{artifact_id}/pages/{index}.png` and `..._thumb.jpg` (chat depends on these).
- **Do NOT add a `parse_status` field to any aggregate** — parse state is observed via Temporal (`GET /artifacts/{id}/workflows`).
- **PyMuPDF stays a dependency** (CSER `cser_pipeline_service.py` + `ExtractDocumentMetadataUseCase` use it directly); only its role as the *upload parser* (`PDFService`) is retired.
- **Page creation must be idempotent:** deterministic page IDs `uuid5(NAMESPACE_URL, f"docu-store/artifact/{artifact_id}/page/{index}")`.
- **Temporal task queue for parsing:** `"artifact_processing"` (the queue the worker already serves).
- Tests live under `tests/` mirroring source; async tests use `@pytest.mark.asyncio`; reuse fakes from `tests/mocks.py` (`MockPageRepository`, `MockArtifactRepository`, `MockWorkflowOrchestrator`) and fixtures from `tests/conftest.py` (`sample_artifact`).

---

## PHASE 0 — Build the new path alongside the old (nothing wired into the live flow yet)

### Task 1: Parse contract — `ParsedDocument` IR, `DocumentParser` port, block linearization

**Files:**
- Create: `application/dtos/parsed_document.py`
- Create: `application/ports/document_parser.py`
- Test: `tests/application/test_parsed_document.py`

**Interfaces:**
- Produces: `Block`, `ParsedDocument`, `RenderedPage`, `ParseResult` (Pydantic/dataclass); `linearize_blocks(blocks: list[Block]) -> str`; `DocumentParser` Protocol with `parse(self, storage_key: str) -> ParseResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/application/test_parsed_document.py
from application.dtos.parsed_document import Block, ParsedDocument, linearize_blocks


def test_parsed_document_json_round_trip():
    doc = ParsedDocument(
        source_mime="application/pdf",
        blocks=[
            Block(type="heading", text="Intro", level=1, source_page_index=0),
            Block(type="paragraph", text="Hello world.", source_page_index=0),
        ],
    )
    restored = ParsedDocument.model_validate_json(doc.model_dump_json())
    assert restored == doc


def test_linearize_heading_and_paragraph():
    out = linearize_blocks([
        Block(type="heading", text="Methods", level=2),
        Block(type="paragraph", text="We did X."),
    ])
    assert "## Methods" in out
    assert "We did X." in out


def test_linearize_table_to_markdown():
    out = linearize_blocks([
        Block(type="table", rows=[["Cmpd", "IC50"], ["X", "5 nM"]], source_page_index=0),
    ])
    assert "| Cmpd | IC50 |" in out
    assert "| X | 5 nM |" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/application/test_parsed_document.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.dtos.parsed_document'`

- [ ] **Step 3: Write minimal implementation**

```python
# application/dtos/parsed_document.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

BlockType = Literal[
    "heading", "paragraph", "list", "table", "figure",
    "caption", "equation", "code", "reference", "footnote", "other",
]


class Block(BaseModel):
    type: BlockType
    text: str = ""
    level: int | None = None            # heading depth
    rows: list[list[str]] | None = None  # table cells
    caption: str | None = None           # figure/table caption
    source_page_index: int | None = None


class ParsedDocument(BaseModel):
    """Structure-only IR. JSON-serializable; persisted as a blob. No image bytes."""

    source_mime: str
    blocks: list[Block] = []


@dataclass
class RenderedPage:
    index: int
    png: bytes
    thumb: bytes | None = None


@dataclass
class ParseResult:
    """Parser output: serializable structure + binary page renders (kept separate)."""

    document: ParsedDocument
    pages: list[RenderedPage] = field(default_factory=list)


def _table_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header, *body = rows
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def linearize_blocks(blocks: list[Block]) -> str:
    """Flatten structured blocks into clean markdown text for the (A)-tier pipeline."""
    parts: list[str] = []
    for b in blocks:
        if b.type == "heading":
            parts.append(f"{'#' * (b.level or 1)} {b.text}".strip())
        elif b.type == "table" and b.rows:
            md = _table_to_markdown(b.rows)
            parts.append(f"{md}\n\n*{b.caption}*" if b.caption else md)
        elif b.type == "figure":
            parts.append(f"[Figure: {b.caption}]" if b.caption else "[Figure]")
        elif b.text:
            parts.append(b.text)
    return "\n\n".join(p for p in parts if p)
```

```python
# application/ports/document_parser.py
from __future__ import annotations

from typing import Protocol

from application.dtos.parsed_document import ParseResult


class DocumentParser(Protocol):
    def parse(self, storage_key: str) -> ParseResult:
        """Parse a blob into a structured ParsedDocument + rendered page images."""
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/application/test_parsed_document.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add application/dtos/parsed_document.py application/ports/document_parser.py tests/application/test_parsed_document.py
git commit -m "feat(ingestion): add ParsedDocument IR + DocumentParser port"
```

---

### Task 2: PDF segmentation — `Segment` + `segment_document()`

**Files:**
- Create: `infrastructure/file_services/segmentation.py`
- Test: `tests/infrastructure/test_segmentation.py`

**Interfaces:**
- Consumes: `ParsedDocument`, `RenderedPage`, `linearize_blocks` (Task 1).
- Produces: `Segment` (dataclass: `index: int`, `text: str`); `segment_document(document: ParsedDocument, pages: list[RenderedPage], mime_type: str) -> list[Segment]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/infrastructure/test_segmentation.py
from application.dtos.parsed_document import Block, ParsedDocument, RenderedPage
from infrastructure.file_services.segmentation import Segment, segment_document


def test_pdf_one_segment_per_rendered_page():
    doc = ParsedDocument(source_mime="application/pdf", blocks=[
        Block(type="paragraph", text="p0", source_page_index=0),
        Block(type="paragraph", text="p1a", source_page_index=1),
        Block(type="paragraph", text="p1b", source_page_index=1),
    ])
    pages = [RenderedPage(index=0, png=b"x"), RenderedPage(index=1, png=b"y")]
    segments = segment_document(doc, pages, mime_type="application/pdf")
    assert [s.index for s in segments] == [0, 1]
    assert segments[0].text == "p0"
    assert "p1a" in segments[1].text and "p1b" in segments[1].text


def test_pdf_image_only_page_yields_empty_text_segment():
    doc = ParsedDocument(source_mime="application/pdf", blocks=[])
    pages = [RenderedPage(index=0, png=b"x")]
    segments = segment_document(doc, pages, mime_type="application/pdf")
    assert len(segments) == 1
    assert segments[0].text == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/infrastructure/test_segmentation.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# infrastructure/file_services/segmentation.py
from __future__ import annotations

from dataclasses import dataclass

from application.dtos.parsed_document import ParsedDocument, RenderedPage, linearize_blocks


@dataclass
class Segment:
    index: int
    text: str


def segment_document(
    document: ParsedDocument,
    pages: list[RenderedPage],
    mime_type: str,
) -> list[Segment]:
    """Split a parsed document into processing units (Pages).

    PDF: one Segment per rendered page (parity with today). Text is the linearized
    blocks whose provenance is that page (empty for image-only pages).

    ponytail: PDF-only for now. Phase 2 turns this into per-format dispatch
    (PPTX -> slide, DOCX/HTML -> section/window).
    """
    by_page: dict[int, list] = {}
    for block in document.blocks:
        by_page.setdefault(block.source_page_index, []).append(block)

    return [
        Segment(index=p.index, text=linearize_blocks(by_page.get(p.index, [])))
        for p in pages
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/infrastructure/test_segmentation.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add infrastructure/file_services/segmentation.py tests/infrastructure/test_segmentation.py
git commit -m "feat(ingestion): PDF document segmentation (one Page per page)"
```

---

### Task 3: `DoclingParser` + add the `docling` dependency

**Files:**
- Modify: `pyproject.toml` (add `docling`)
- Create: `infrastructure/file_services/docling_parser.py`
- Test: `tests/infrastructure/test_docling_parser_integration.py`
- Fixture: `tests/fixtures/sample_two_page.pdf` (any small 2-page text PDF; create one if absent)

**Interfaces:**
- Consumes: `BlobStore` (`get_file(key) -> ContextManager[Path]`), `ParseResult`, `ParsedDocument`, `Block`, `RenderedPage`.
- Produces: `DoclingParser(blob_store: BlobStore)` implementing `DocumentParser`.

- [ ] **Step 1: Add the dependency**

Run: `uv add docling`
(Docling pulls its own model weights on first run; `DocumentConverter` is the entry point.)

- [ ] **Step 2: Write the failing integration test**

```python
# tests/infrastructure/test_docling_parser_integration.py
from pathlib import Path

import pytest

from infrastructure.blob_stores.fsspec_blob_store import FsspecBlobStore  # adjust to actual class
from infrastructure.file_services.docling_parser import DoclingParser


@pytest.mark.integration
def test_docling_parses_pdf_into_pages_and_text(tmp_path):
    pdf = Path("tests/fixtures/sample_two_page.pdf").read_bytes()
    store = FsspecBlobStore(base_path=str(tmp_path))  # adjust constructor to actual signature
    import io
    store.put_stream("artifacts/x/source.pdf", io.BytesIO(pdf), mime_type="application/pdf")

    result = DoclingParser(blob_store=store).parse("artifacts/x/source.pdf")

    assert result.document.source_mime == "application/pdf"
    assert len(result.pages) >= 1
    assert result.pages[0].png  # non-empty PNG bytes
    assert any(b.text.strip() for b in result.document.blocks)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/infrastructure/test_docling_parser_integration.py -v`
Expected: FAIL with `ModuleNotFoundError: ... docling_parser`

- [ ] **Step 4: Write the implementation**

```python
# infrastructure/file_services/docling_parser.py
from __future__ import annotations

import io
from typing import TYPE_CHECKING

import structlog

from application.dtos.parsed_document import Block, ParsedDocument, ParseResult, RenderedPage
from application.ports.document_parser import DocumentParser

if TYPE_CHECKING:
    from application.ports.blob_store import BlobStore

log = structlog.get_logger(__name__)

# Map Docling label names -> our Block.type. Extend as needed.
_LABEL_MAP = {
    "title": "heading", "section_header": "heading",
    "paragraph": "paragraph", "text": "paragraph",
    "list_item": "list", "table": "table",
    "picture": "figure", "caption": "caption",
    "formula": "equation", "code": "code",
}

_THUMB_MAX = 400  # px, longest edge


def _make_thumb(png: bytes) -> bytes | None:
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(png))
        img.thumbnail((_THUMB_MAX, _THUMB_MAX))
        out = io.BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=80)
        return out.getvalue()
    except Exception:
        log.warning("docling_parser.thumb_failed", exc_info=True)
        return None


class DoclingParser(DocumentParser):
    """Parse documents into a structured ParsedDocument using Docling."""

    def __init__(self, blob_store: BlobStore) -> None:
        self.blob_store = blob_store
        self._converter = None

    def _get_converter(self):
        # Lazy: heavy import + model setup. Configure page-image generation on.
        if self._converter is None:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption
            opts = PdfPipelineOptions()
            opts.generate_page_images = True
            opts.images_scale = 2.0  # ~144 DPI, matches CSER's render scale
            self._converter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)},
            )
        return self._converter

    def parse(self, storage_key: str) -> ParseResult:
        with self.blob_store.get_file(storage_key) as path:
            conv = self._get_converter().convert(str(path))
        dl_doc = conv.document

        blocks: list[Block] = []
        for item, _level in dl_doc.iterate_items():
            block = self._to_block(item)
            if block is not None:
                blocks.append(block)

        pages: list[RenderedPage] = []
        for page_no in sorted(dl_doc.pages):  # 1-based in Docling
            png = self._page_png(dl_doc, page_no)
            if png is not None:
                pages.append(RenderedPage(index=page_no - 1, png=png, thumb=_make_thumb(png)))

        return ParseResult(
            document=ParsedDocument(source_mime="application/pdf", blocks=blocks),
            pages=pages,
        )

    def _to_block(self, item) -> Block | None:
        label = getattr(getattr(item, "label", None), "value", None) or getattr(item, "label", None)
        btype = _LABEL_MAP.get(str(label), "other")
        page_idx = None
        prov = getattr(item, "prov", None)
        if prov:
            page_idx = prov[0].page_no - 1
        if btype == "table":
            rows = self._table_rows(item)
            return Block(type="table", rows=rows, source_page_index=page_idx)
        text = getattr(item, "text", "") or ""
        if not text and btype not in ("figure",):
            return None
        return Block(type=btype, text=text, source_page_index=page_idx)

    def _table_rows(self, item) -> list[list[str]]:
        try:
            df = item.export_to_dataframe()
            return [list(df.columns)] + df.astype(str).values.tolist()
        except Exception:
            return []

    def _page_png(self, dl_doc, page_no: int) -> bytes | None:
        try:
            img = dl_doc.pages[page_no].image.pil_image  # PIL image
            out = io.BytesIO()
            img.convert("RGB").save(out, format="PNG")
            return out.getvalue()
        except Exception:
            log.warning("docling_parser.page_image_failed", page_no=page_no, exc_info=True)
            return None
```

> **Note for implementer:** Docling's exact item/table/page-image accessors vary by version. Open the installed `docling` and confirm `iterate_items()`, `item.prov[0].page_no`, `item.export_to_dataframe()`, and `pages[n].image.pil_image`. The *contract* (return `ParseResult` with one `RenderedPage` per page (0-based index) and `Block`s tagged by `source_page_index`) is fixed; adapt the accessors to match.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/infrastructure/test_docling_parser_integration.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock infrastructure/file_services/docling_parser.py tests/infrastructure/test_docling_parser_integration.py tests/fixtures/sample_two_page.pdf
git commit -m "feat(ingestion): DoclingParser (PDF -> ParsedDocument + page images)"
```

---

### Task 4: Deterministic page IDs (retry-safe creation)

**Files:**
- Modify: `domain/aggregates/page.py` (`create` classmethod, ~lines 26-42)
- Modify: `application/dtos/page_dtos.py` (`CreatePageRequest`, ~lines 11-14)
- Modify: `application/use_cases/page_use_cases.py` (`CreatePageUseCase.execute`, the `Page.create(...)` call ~line 63)
- Test: `tests/domain/test_page_deterministic_id.py`, add a case to `tests/application/test_page_use_cases.py`

**Interfaces:**
- Produces: `Page.create(..., page_id: UUID | None = None)`; `CreatePageRequest.page_id: UUID | None`; `CreatePageUseCase` forwards `request.page_id`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_page_deterministic_id.py
from uuid import uuid4

from domain.aggregates.page import Page


def test_create_with_explicit_id_uses_it():
    pid, aid = uuid4(), uuid4()
    page = Page.create(name="Page 1", artifact_id=aid, index=0, page_id=pid)
    assert page.id == pid


def test_create_without_id_autogenerates():
    page = Page.create(name="Page 1", artifact_id=uuid4(), index=0)
    assert page.id is not None
```

```python
# tests/application/test_page_use_cases.py  (add this test)
from uuid import uuid4
from returns.result import Success
from application.dtos.page_dtos import CreatePageRequest
from application.use_cases.page_use_cases import CreatePageUseCase
from tests.mocks import MockPageRepository, MockArtifactRepository


@pytest.mark.asyncio
async def test_create_page_honors_explicit_page_id(sample_artifact):
    page_repo, artifact_repo = MockPageRepository(), MockArtifactRepository()
    artifact_repo.save(sample_artifact)
    pid = uuid4()
    uc = CreatePageUseCase(page_repo, artifact_repo)
    req = CreatePageRequest(name="P1", artifact_id=sample_artifact.id, index=0, page_id=pid)
    result = await uc.execute(req)
    assert isinstance(result, Success)
    assert result.unwrap().page_id == pid
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/domain/test_page_deterministic_id.py tests/application/test_page_use_cases.py::test_create_page_honors_explicit_page_id -v`
Expected: FAIL (`Page.create() got an unexpected keyword argument 'page_id'`)

- [ ] **Step 3: Implement**

In `domain/aggregates/page.py`, change `create` to accept an optional id and route through `_create` when given:

```python
    @classmethod
    def create(
        cls,
        name: str,
        artifact_id: UUID,
        index: int = 0,
        workspace_id: UUID | None = None,
        owner_id: UUID | None = None,
        page_id: UUID | None = None,
    ) -> Page:
        """Create a new Page aggregate (Factory Method)."""
        if page_id is not None:
            return cls._create(
                cls.Created,
                id=page_id,
                name=name,
                artifact_id=artifact_id,
                index=index,
                workspace_id=workspace_id,
                owner_id=owner_id,
            )
        return cls(name=name, artifact_id=artifact_id, index=index,
                   workspace_id=workspace_id, owner_id=owner_id)
```

In `application/dtos/page_dtos.py`:

```python
class CreatePageRequest(BaseModel):
    name: str
    artifact_id: UUID
    index: int = 0
    page_id: UUID | None = None
```

In `application/use_cases/page_use_cases.py` (`CreatePageUseCase.execute`, the `Page.create(...)` call):

```python
        page = Page.create(
            name=request.name,
            artifact_id=request.artifact_id,
            index=request.index,
            page_id=request.page_id,
            # keep existing workspace_id / owner_id args from auth, if present
        )
```

> **Note:** `_create(event_class, *, id, **kwargs)` is the `eventsourcing` mechanism for explicit aggregate IDs. If the installed version differs, the requirement is simply: *same `(artifact_id, index)` ⇒ same page id.*

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/domain/test_page_deterministic_id.py tests/application/test_page_use_cases.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add domain/aggregates/page.py application/dtos/page_dtos.py application/use_cases/page_use_cases.py tests/domain/test_page_deterministic_id.py tests/application/test_page_use_cases.py
git commit -m "feat(page): optional deterministic page_id for idempotent creation"
```

---

### Task 5: `ParseArtifactUseCase` (the core)

**Files:**
- Create: `application/use_cases/parse_artifact_use_case.py`
- Test: `tests/application/test_parse_artifact_use_case.py`

**Interfaces:**
- Consumes: `DocumentParser`, `BlobStore`, `ArtifactRepository` (read `mime_type` + `storage_location`), `CreatePageUseCase`, `UpdateTextMentionUseCase`, `AddPagesUseCase`, `segment_document`, `MimeType`.
- Produces: `ParseArtifactUseCase(parsers, blob_store, artifact_repository, create_page_use_case, update_text_mention_use_case, add_pages_use_case)`; `async execute(self, artifact_id: UUID) -> Result[list[UUID], AppError]`; module helper `page_id_for(artifact_id, index) -> UUID`.

- [ ] **Step 1: Write the failing test**

```python
# tests/application/test_parse_artifact_use_case.py
import io
from uuid import uuid4

import pytest
from returns.result import Success

from application.dtos.artifact_dtos import CreateArtifactRequest
from application.dtos.parsed_document import Block, ParsedDocument, ParseResult, RenderedPage
from application.use_cases.artifact_use_cases import AddPagesUseCase, CreateArtifactUseCase
from application.use_cases.page_use_cases import CreatePageUseCase, UpdateTextMentionUseCase
from application.use_cases.parse_artifact_use_case import ParseArtifactUseCase, page_id_for
from domain.value_objects.artifact_type import ArtifactType  # use any valid member below
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
        artifact_type=ArtifactType.PUBLICATION,  # any valid ArtifactType member
        mime_type=MimeType.PDF,
        storage_location="artifacts/x/source.pdf",
    )
    return (await uc.execute(req)).unwrap().artifact_id


def _build_uc(parsers, blob, page_repo, artifact_repo):
    return ParseArtifactUseCase(
        parsers=parsers,
        blob_store=blob,
        artifact_repository=artifact_repo,
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
    page_repo, artifact_repo, blob = MockPageRepository(), MockArtifactRepository(), FakeBlobStore()
    artifact_id = await _make_artifact(artifact_repo)
    uc = _build_uc({MimeType.PDF: FakeParser()}, blob, page_repo, artifact_repo)

    first = await uc.execute(artifact_id)
    second = await uc.execute(artifact_id)  # simulates Temporal retry

    assert isinstance(second, Success)
    assert first.unwrap() == second.unwrap()  # same deterministic id, no duplicate
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/application/test_parse_artifact_use_case.py -v`
Expected: FAIL with `ModuleNotFoundError: ... parse_artifact_use_case`

- [ ] **Step 3: Implement**

```python
# application/use_cases/parse_artifact_use_case.py
from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, UUID, uuid5

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from application.dtos.page_dtos import CreatePageRequest
from domain.value_objects.text_mention import TextMention
from infrastructure.file_services.segmentation import segment_document

if TYPE_CHECKING:
    from application.ports.blob_store import BlobStore
    from application.ports.document_parser import DocumentParser
    from application.use_cases.artifact_use_cases import AddPagesUseCase
    from application.use_cases.page_use_cases import CreatePageUseCase, UpdateTextMentionUseCase
    from domain.value_objects.mime_type import MimeType

log = structlog.get_logger(__name__)


def page_id_for(artifact_id: UUID, index: int) -> UUID:
    return uuid5(NAMESPACE_URL, f"docu-store/artifact/{artifact_id}/page/{index}")


class ParseArtifactUseCase:
    """Parse an artifact into a structured document and create its Pages (idempotent)."""

    def __init__(
        self,
        parsers: dict[MimeType, DocumentParser],
        blob_store: BlobStore,
        artifact_repository,
        create_page_use_case: CreatePageUseCase,
        update_text_mention_use_case: UpdateTextMentionUseCase,
        add_pages_use_case: AddPagesUseCase,
    ) -> None:
        self.parsers = parsers
        self.blob_store = blob_store
        self.artifact_repository = artifact_repository
        self.create_page = create_page_use_case
        self.update_text_mention = update_text_mention_use_case
        self.add_pages = add_pages_use_case

    async def execute(self, artifact_id: UUID) -> Result[list[UUID], AppError]:
        artifact = await self.artifact_repository.get(artifact_id)  # confirm accessor name
        parser = self.parsers.get(artifact.mime_type)
        if parser is None:
            return Failure(AppError("validation", f"No parser for MIME type: {artifact.mime_type}"))

        parsed = parser.parse(artifact.storage_location)

        # Persist page images (same keys chat already uses).
        for page in parsed.pages:
            self.blob_store.put_stream(
                f"artifacts/{artifact_id}/pages/{page.index}.png",
                io.BytesIO(page.png), mime_type="image/png",
            )
            if page.thumb:
                self.blob_store.put_stream(
                    f"artifacts/{artifact_id}/pages/{page.index}_thumb.jpg",
                    io.BytesIO(page.thumb), mime_type="image/jpeg",
                )

        # Persist the structure-only IR blob (retained for future (B)-tier features).
        self.blob_store.put_stream(
            f"artifacts/{artifact_id}/parsed/document.json",
            io.BytesIO(parsed.document.model_dump_json().encode()),
            mime_type="application/json",
        )

        segments = segment_document(parsed.document, parsed.pages, str(artifact.mime_type))
        now = datetime.now(tz=UTC)
        page_ids: list[UUID] = []

        for seg in segments:
            pid = page_id_for(artifact_id, seg.index)
            page_ids.append(pid)
            create_res = await self.create_page.execute(
                CreatePageRequest(
                    name=f"Page {seg.index + 1}",
                    artifact_id=artifact_id,
                    index=seg.index,
                    page_id=pid,
                ),
            )
            # Idempotent: a retry re-creating an existing page id fails -> treat as done.
            if isinstance(create_res, Failure):
                log.info("parse.page_exists_skipping_create", page_id=str(pid))
            if seg.text.strip():
                await self.update_text_mention.execute(
                    page_id=pid,
                    text_mention=TextMention(
                        text=seg.text, date_extracted=now, model_name="DoclingParser",
                        confidence=None, additional_model_params=None, pipeline_run_id=None,
                    ),
                )

        if page_ids:
            await self.add_pages.execute(artifact_id=artifact_id, page_ids=page_ids)

        return Success(page_ids)
```

> **Note:** confirm the artifact read accessor — the repo method (`get`/`load`) and the aggregate attributes (`artifact.mime_type`, `artifact.storage_location`). These exist on the `Artifact` aggregate (set at creation); adjust names if they differ.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/application/test_parse_artifact_use_case.py -v`
Expected: PASS (2 tests). If `MockArtifactRepository.get` is missing/async-mismatched, align the call with the mock's accessor.

- [ ] **Step 5: Commit**

```bash
git add application/use_cases/parse_artifact_use_case.py tests/application/test_parse_artifact_use_case.py
git commit -m "feat(ingestion): ParseArtifactUseCase (parse -> IR -> idempotent pages)"
```

---

### Task 6: Durable layer — `ParseArtifactWorkflow`, `parse_artifact` activity, orchestrator method + port + mock

**Files:**
- Rewrite: `infrastructure/temporal/workflows/artifact_processing.py` (replace `ProcessArtifactWorkflow` with `ParseArtifactWorkflow`)
- Create: `infrastructure/temporal/activities/parse_activities.py`
- Modify: `application/ports/workflow_orchestrator.py` (add `start_artifact_parse_workflow`)
- Modify: `infrastructure/temporal/orchestrator.py` (implement it)
- Modify: `tests/mocks.py` (`MockWorkflowOrchestrator`: add method + `artifact_parse_calls`)

**Interfaces:**
- Consumes: `ParseArtifactUseCase` (Task 5).
- Produces: `ParseArtifactWorkflow.run(self, artifact_id: str) -> dict`; `create_parse_artifact_activity(use_case) -> Callable[[str], dict]` (activity name `"parse_artifact"`); `WorkflowOrchestrator.start_artifact_parse_workflow(self, artifact_id: UUID) -> None`.

- [ ] **Step 1: Write the workflow** (rewrite the dead file)

```python
# infrastructure/temporal/workflows/artifact_processing.py
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="ParseArtifactWorkflow")
class ParseArtifactWorkflow:
    """Durable parse of an artifact into its structured document + Pages."""

    @workflow.run
    async def run(self, artifact_id: str) -> dict:
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=5),
            maximum_interval=timedelta(seconds=60),
            maximum_attempts=3,
            backoff_coefficient=2.0,
        )
        result = await workflow.execute_activity(
            "parse_artifact",
            artifact_id,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=retry_policy,
        )
        workflow.logger.info(f"Parse workflow completed for artifact_id={artifact_id}")
        return result
```

- [ ] **Step 2: Write the activity factory**

```python
# infrastructure/temporal/activities/parse_activities.py
from __future__ import annotations

from typing import TYPE_CHECKING, Callable
from uuid import UUID

import structlog
from returns.result import Success
from temporalio import activity

if TYPE_CHECKING:
    from application.use_cases.parse_artifact_use_case import ParseArtifactUseCase

logger = structlog.get_logger(__name__)


def create_parse_artifact_activity(use_case: ParseArtifactUseCase) -> Callable[[str], dict]:
    @activity.defn(name="parse_artifact")
    async def parse_artifact_activity(artifact_id: str) -> dict:
        logger.info("parse_artifact_activity_start", artifact_id=artifact_id)
        result = await use_case.execute(artifact_id=UUID(artifact_id))
        if isinstance(result, Success):
            page_ids = result.unwrap()
            return {"status": "success", "artifact_id": artifact_id, "page_count": len(page_ids)}
        error = result.failure()
        # Raise so Temporal retries on transient failures.
        raise RuntimeError(f"{error.category}: {error.message}")

    return parse_artifact_activity
```

- [ ] **Step 3: Add the orchestrator method (port + impl + mock)**

In `application/ports/workflow_orchestrator.py` add to the Protocol:

```python
    async def start_artifact_parse_workflow(self, artifact_id: UUID) -> None: ...
```

In `infrastructure/temporal/orchestrator.py`:

```python
    async def start_artifact_parse_workflow(self, artifact_id: UUID) -> None:
        await self._ensure_client()
        await self._client.start_workflow(
            "ParseArtifactWorkflow",
            str(artifact_id),
            id=f"artifact-parse-{artifact_id}",
            task_queue="artifact_processing",
        )
```

In `tests/mocks.py` (`MockWorkflowOrchestrator`):

```python
        self.artifact_parse_calls: list[UUID] = []   # in __init__

    async def start_artifact_parse_workflow(self, artifact_id: UUID) -> None:
        self.artifact_parse_calls.append(artifact_id)
```

- [ ] **Step 4: Verify imports/typing**

Run: `uv run python -c "import infrastructure.temporal.workflows.artifact_processing as w; import infrastructure.temporal.activities.parse_activities as a; print(w.ParseArtifactWorkflow, a.create_parse_artifact_activity)"`
Expected: prints the workflow class and factory function with no import errors.

- [ ] **Step 5: Commit**

```bash
git add infrastructure/temporal/workflows/artifact_processing.py infrastructure/temporal/activities/parse_activities.py application/ports/workflow_orchestrator.py infrastructure/temporal/orchestrator.py tests/mocks.py
git commit -m "feat(ingestion): ParseArtifactWorkflow + parse_artifact activity + orchestrator"
```

---

### Task 7: `TriggerArtifactParseUseCase`

**Files:**
- Create: `application/workflow_use_cases/trigger_artifact_parse_use_case.py`
- Test: add to `tests/application/test_workflow_use_cases.py`

**Interfaces:**
- Consumes: `WorkflowOrchestrator.start_artifact_parse_workflow` (Task 6).
- Produces: `TriggerArtifactParseUseCase(workflow_orchestrator)`; `async execute(self, artifact_id: UUID) -> WorkflowStartedResponse`.

- [ ] **Step 1: Write the failing test**

```python
# tests/application/test_workflow_use_cases.py  (add)
from uuid import uuid4
import pytest
from application.dtos.workflow_dtos import WorkflowStartedResponse
from application.workflow_use_cases.trigger_artifact_parse_use_case import TriggerArtifactParseUseCase
from tests.mocks import MockWorkflowOrchestrator


@pytest.mark.asyncio
async def test_trigger_artifact_parse_starts_workflow():
    orchestrator = MockWorkflowOrchestrator()
    uc = TriggerArtifactParseUseCase(orchestrator)
    artifact_id = uuid4()

    result = await uc.execute(artifact_id=artifact_id)

    assert isinstance(result, WorkflowStartedResponse)
    assert result.workflow_id == f"artifact-parse-{artifact_id}"
    assert orchestrator.artifact_parse_calls == [artifact_id]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/application/test_workflow_use_cases.py::test_trigger_artifact_parse_starts_workflow -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# application/workflow_use_cases/trigger_artifact_parse_use_case.py
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from application.dtos.workflow_dtos import WorkflowStartedResponse

if TYPE_CHECKING:
    from application.ports.workflow_orchestrator import WorkflowOrchestrator


class TriggerArtifactParseUseCase:
    """Trigger the durable parse workflow for an artifact."""

    def __init__(self, workflow_orchestrator: WorkflowOrchestrator) -> None:
        self.workflow_orchestrator = workflow_orchestrator

    async def execute(self, artifact_id: UUID) -> WorkflowStartedResponse:
        await self.workflow_orchestrator.start_artifact_parse_workflow(artifact_id=artifact_id)
        return WorkflowStartedResponse(workflow_id=f"artifact-parse-{artifact_id}")
```

> **Note:** match the exact `WorkflowStartedResponse` constructor used by sibling trigger use cases (some set `status="started"`). Mirror `TriggerCompoundExtractionUseCase`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/application/test_workflow_use_cases.py::test_trigger_artifact_parse_starts_workflow -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add application/workflow_use_cases/trigger_artifact_parse_use_case.py tests/application/test_workflow_use_cases.py
git commit -m "feat(ingestion): TriggerArtifactParseUseCase"
```

---

### Task 8: Register new components (DI + worker) — still not routed from the live event flow

**Files:**
- Modify: `infrastructure/di/container.py` (register `DoclingParser`, the `parsers` dict, `ParseArtifactUseCase`, `TriggerArtifactParseUseCase`)
- Modify: `infrastructure/temporal/worker.py` (resolve `ParseArtifactUseCase`, build `parse_artifact` activity, add `ParseArtifactWorkflow` + activity to the worker lists)

**Interfaces:**
- Consumes: all of Tasks 1–7.
- Produces: container resolves `ParseArtifactUseCase` and `TriggerArtifactParseUseCase`; worker serves `ParseArtifactWorkflow` + `parse_artifact`.

- [ ] **Step 1: DI registrations** (in `infrastructure/di/container.py`)

```python
from infrastructure.file_services.docling_parser import DoclingParser
from application.ports.document_parser import DocumentParser
from application.use_cases.parse_artifact_use_case import ParseArtifactUseCase
from application.workflow_use_cases.trigger_artifact_parse_use_case import TriggerArtifactParseUseCase
from domain.value_objects.mime_type import MimeType

container[DoclingParser] = lambda c: DoclingParser(blob_store=c[BlobStore])
container[ParseArtifactUseCase] = lambda c: ParseArtifactUseCase(
    parsers={MimeType.PDF: c[DoclingParser]},
    blob_store=c[BlobStore],
    artifact_repository=c[ArtifactRepository],
    create_page_use_case=c[CreatePageUseCase],
    update_text_mention_use_case=c[UpdateTextMentionUseCase],
    add_pages_use_case=c[AddPagesUseCase],
)
container[TriggerArtifactParseUseCase] = lambda c: TriggerArtifactParseUseCase(
    workflow_orchestrator=c[WorkflowOrchestrator],
)
```

- [ ] **Step 2: Worker registration** (in `infrastructure/temporal/worker.py`)

Resolve the use case (with the other `container[...]` resolutions, ~line 124):
```python
parse_artifact_use_case = container[ParseArtifactUseCase]
```
Build the activity (with the other factory calls, ~line 153):
```python
parse_artifact_activity = create_parse_artifact_activity(use_case=parse_artifact_use_case)
```
Add the import near the other activity-factory imports:
```python
from infrastructure.temporal.activities.parse_activities import create_parse_artifact_activity
from infrastructure.temporal.workflows.artifact_processing import ParseArtifactWorkflow
```
Add `ParseArtifactWorkflow` to `workflows=[...]` and `parse_artifact_activity` to `activities=[...]`.

- [ ] **Step 3: Verify container + worker import**

Run: `uv run python -c "from infrastructure.di.container import create_container; c = create_container(); from application.use_cases.parse_artifact_use_case import ParseArtifactUseCase; from application.workflow_use_cases.trigger_artifact_parse_use_case import TriggerArtifactParseUseCase; print(c[ParseArtifactUseCase], c[TriggerArtifactParseUseCase])"`
Expected: prints both instances, no errors.

Run: `uv run pytest -q`
Expected: full suite green.

- [ ] **Step 4: Commit**

```bash
git add infrastructure/di/container.py infrastructure/temporal/worker.py
git commit -m "chore(ingestion): wire DoclingParser, ParseArtifactUseCase, parse workflow into DI + worker"
```

---

### Task 9: Docling quality gate (decision point — do not start Phase 1 until this passes)

**Files:**
- Create: `tests/infrastructure/test_docling_vs_pymupdf.py` (informational comparison; marked `integration`)

**Interfaces:** none (verification only).

- [ ] **Step 1: Write the comparison harness**

```python
# tests/infrastructure/test_docling_vs_pymupdf.py
"""Phase-0 gate: compare Docling vs PyMuPDF text/page extraction on real PDFs.
Run against a representative scientific-PDF corpus before cutting over (Phase 1).
Drop sample PDFs into tests/fixtures/corpus/ and run with: -m integration -s
"""
from pathlib import Path

import pytest


@pytest.mark.integration
def test_report_docling_vs_pymupdf(tmp_path, capsys):
    import io
    from infrastructure.blob_stores.fsspec_blob_store import FsspecBlobStore  # adjust
    from infrastructure.file_services.docling_parser import DoclingParser
    from infrastructure.file_services.py_mu_pfd_service import PyMuPDFService

    corpus = sorted(Path("tests/fixtures/corpus").glob("*.pdf"))
    if not corpus:
        pytest.skip("no corpus PDFs in tests/fixtures/corpus/")

    store = FsspecBlobStore(base_path=str(tmp_path))
    docling, pymupdf = DoclingParser(store), PyMuPDFService(store)

    for pdf in corpus:
        key = f"artifacts/{pdf.stem}/source.pdf"
        store.put_stream(key, io.BytesIO(pdf.read_bytes()), mime_type="application/pdf")
        d = docling.parse(key)
        p = pymupdf.parse(storage_key=key)
        d_chars = sum(len(b.text) for b in d.document.blocks)
        p_chars = len(p.combined_content or "")
        print(f"{pdf.name}: docling_pages={len(d.pages)} pymupdf_pages={len(p.pages or [])} "
              f"docling_chars={d_chars} pymupdf_chars={p_chars}")
```

- [ ] **Step 2: Run the gate on your corpus**

Run: `uv run pytest tests/infrastructure/test_docling_vs_pymupdf.py -m integration -s`
Expected: a per-file report. **Decision:** page counts match and Docling char counts are comparable-or-better (especially on multi-column / tables). If Docling regresses badly on your real documents, stop and revisit the parser choice before Phase 1.

- [ ] **Step 3: Commit**

```bash
git add tests/infrastructure/test_docling_vs_pymupdf.py
git commit -m "test(ingestion): Docling vs PyMuPDF extraction gate"
```

---

## PHASE 1 — Cut over to the new path (atomic) and retire the old one

> Do not start until Task 9 passes on your real corpus.

### Task 10: Cutover — thin the saga + route `Artifact.Created` to the parse trigger

**Files:**
- Modify: `application/sagas/artifact_upload_saga.py` (remove parse + `_process_pdf_pages`)
- Modify: `infrastructure/di/container.py` (saga deps shrink)
- Modify: `infrastructure/pipeline_worker.py` (`Artifact.Created` → `TriggerArtifactParseUseCase`)
- Test: `tests/application/test_artifact_upload_saga.py`

**Interfaces:**
- Consumes: `TriggerArtifactParseUseCase` (Task 7).
- Produces: thinned `ArtifactUploadSaga(upload_blob_use_case, create_artifact_use_case, permission_registrar)`.

- [ ] **Step 1: Write the failing saga test**

```python
# tests/application/test_artifact_upload_saga.py
import io
import pytest
from returns.result import Success
from application.dtos.blob_dtos import UploadBlobRequest
from application.sagas.artifact_upload_saga import ArtifactUploadSaga
from domain.value_objects.artifact_type import ArtifactType
# Build saga from real use cases over mock repos/blob store (see test_parse_artifact_use_case helpers).


@pytest.mark.asyncio
async def test_saga_uploads_and_creates_artifact_without_parsing(saga_under_test):
    saga, calls = saga_under_test  # fixture: thinned saga + parse-call spy
    req = UploadBlobRequest(artifact_type=ArtifactType.PUBLICATION, filename="x.pdf",
                            mime_type="application/pdf")
    result = await saga.execute(io.BytesIO(b"%PDF-1.4 ..."), req)
    assert isinstance(result, Success)
    artifact = result.unwrap()
    assert artifact.pages in (None, [])      # no pages created synchronously
    assert calls.pdf_parse_count == 0        # saga never parses
```

> Build `saga_under_test` mirroring the arrange in `test_parse_artifact_use_case.py` (mock repos + `FakeBlobStore`). The saga should no longer accept a `pdf_service`/`create_page`/`add_pages`/`update_text_mention`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/application/test_artifact_upload_saga.py -v`
Expected: FAIL (saga still requires the removed deps / still parses)

- [ ] **Step 3: Thin the saga**

Replace `ArtifactUploadSaga` so `__init__` takes only `upload_blob_use_case`, `create_artifact_use_case`, `permission_registrar`, and `execute` does: upload blob → create artifact → register permissions → return `artifact_response` (with `pages` unset). Delete `_process_pdf_pages` and the `pdf_service.parse(...)` call entirely.

- [ ] **Step 4: Shrink the saga's DI registration** (`infrastructure/di/container.py`)

```python
container[ArtifactUploadSaga] = lambda c: ArtifactUploadSaga(
    upload_blob_use_case=c[UploadBlobUseCase],
    create_artifact_use_case=c[CreateArtifactUseCase],
    permission_registrar=c[PermissionRegistrar],
)
```

- [ ] **Step 5: Route the event** (`infrastructure/pipeline_worker.py`)

Resolve the trigger near the other DI resolutions (~lines 85-96):
```python
trigger_artifact_parse_use_case = container[TriggerArtifactParseUseCase]
```
Replace the `case Artifact.Created():` body (~lines 182-199) so it calls:
```python
        await trigger_artifact_parse_use_case.execute(
            artifact_id=domain_event.originator_id,
        )
```
(Remove the `log_artifact_sample_use_case.execute(...)` call here.)

- [ ] **Step 6: Run tests + verify routing**

Run: `uv run pytest tests/application/test_artifact_upload_saga.py -v && uv run pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 7: Commit**

```bash
git add application/sagas/artifact_upload_saga.py infrastructure/di/container.py infrastructure/pipeline_worker.py tests/application/test_artifact_upload_saga.py
git commit -m "feat(ingestion): async cutover - thin upload saga, parse on Artifact.Created"
```

---

### Task 11: Relax the MIME gate to an extensible supported-set

**Files:**
- Modify: `application/use_cases/blob_use_cases.py` (~lines 29-36)
- Test: add to `tests/application/test_blob_use_cases.py`

**Interfaces:**
- Produces: `SUPPORTED_UPLOAD_MIME_TYPES: frozenset[str]` (Phase 1 value: `{MimeType.PDF}`; Phase 2 adds PPTX/DOCX when their parsers land).

- [ ] **Step 1: Write the failing test**

```python
# tests/application/test_blob_use_cases.py  (add)
import io
import pytest
from returns.result import Failure, Success
from application.dtos.blob_dtos import UploadBlobRequest
from application.use_cases.blob_use_cases import UploadBlobUseCase
from domain.value_objects.artifact_type import ArtifactType


def test_pdf_accepted_unsupported_rejected(tmp_path):
    from infrastructure.blob_stores.fsspec_blob_store import FsspecBlobStore  # adjust
    uc = UploadBlobUseCase(blob_store=FsspecBlobStore(base_path=str(tmp_path)))
    ok = uc.execute(io.BytesIO(b"%PDF"), UploadBlobRequest(
        artifact_type=ArtifactType.PUBLICATION, filename="a.pdf", mime_type="application/pdf"))
    assert isinstance(ok, Success)
    bad = uc.execute(io.BytesIO(b"x"), UploadBlobRequest(
        artifact_type=ArtifactType.PUBLICATION, filename="a.xyz", mime_type="application/x-bogus"))
    assert isinstance(bad, Failure)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/application/test_blob_use_cases.py -v`
Expected: FAIL if the test references behavior not yet present (or passes trivially if PDF-only already — then the value is the named constant for Phase 2 extensibility).

- [ ] **Step 3: Implement** (`application/use_cases/blob_use_cases.py`)

```python
from domain.value_objects.mime_type import MimeType

SUPPORTED_UPLOAD_MIME_TYPES: frozenset[str] = frozenset({MimeType.PDF.value})

# replace the lines 29-36 check:
        if cmd.mime_type not in SUPPORTED_UPLOAD_MIME_TYPES:
            return Failure(AppError(
                "validation", f"Unsupported MIME type for upload: {cmd.mime_type}",
            ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/application/test_blob_use_cases.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add application/use_cases/blob_use_cases.py tests/application/test_blob_use_cases.py
git commit -m "refactor(ingestion): MIME gate as extensible supported-set (PDF for now)"
```

---

### Task 12: Remove the dead synchronous path

**Files:**
- Delete: `infrastructure/temporal/activities/artifact_activities.py` (toy `log_*` activities)
- Delete: `application/workflow_use_cases/log_artifcat_sample_use_case.py` (`LogArtifactSampleUseCase`)
- Modify: `infrastructure/temporal/worker.py` (remove `log_mime_type_activity`, `log_storage_location_activity` from the activities list and their imports)
- Modify: `infrastructure/temporal/orchestrator.py` (remove `start_artifact_processing_workflow`)
- Modify: `infrastructure/di/container.py` (remove `PDFService`/`PyMuPDFService` registration **as the upload parser**, remove `LogArtifactSampleUseCase` registration)
- Modify: `infrastructure/pipeline_worker.py` (remove the now-unused `log_artifact_sample_use_case` resolution/import)

**Interfaces:** none new (deletion + cleanup).

- [ ] **Step 1: Grep for every reference before deleting**

Run: `grep -rn "LogArtifactSampleUseCase\|log_mime_type_activity\|log_storage_location_activity\|start_artifact_processing_workflow\|ProcessArtifactWorkflow\|PDFService\b" application infrastructure interfaces`
Expected: a list of all call sites. Each must be removed or already replaced by Tasks 6/10.

- [ ] **Step 2: Delete + clean up**

Remove the files and references above. Keep `PyMuPDFService` the class file (still imported by CSER/metadata if they use it) — but if nothing references it after removing the `PDFService` registration, delete `application/ports/pdf_service.py`, `application/dtos/pdf_dtos.py`, and `infrastructure/file_services/py_mu_pfd_service.py` too. (Confirm via the grep — `cser_pipeline_service.py` and `extract_document_metadata_use_case.py` use PyMuPDF's `fitz` directly, not `PyMuPDFService`, so the service class is very likely safe to delete. The `fitz` dependency stays.)

- [ ] **Step 3: Verify nothing dangling + suite green**

Run: `grep -rn "LogArtifactSampleUseCase\|start_artifact_processing_workflow\|ProcessArtifactWorkflow" application infrastructure interfaces`
Expected: no matches.

Run: `uv run pytest -q`
Expected: full suite green.

Run: `uv run python -c "from infrastructure.temporal.worker import *"` (or the worker's entrypoint import)
Expected: imports cleanly (no references to deleted activities/workflow).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(ingestion): remove dead synchronous PDF parse path"
```

---

## Out of scope (separate plans)

- **Phase 2** — PPTX + DOCX parsers/segmenters; LibreOffice full-page rendering for non-visual formats; CSER reading the stored page image for non-PDF; extend `SUPPORTED_UPLOAD_MIME_TYPES` + the `parsers` dict.
- **Phase 3** — HTML/JATS ingestion; structure-aware chunking on IR section boundaries.
- **(B) tier** — first-class structured tables/figures (retrieval payloads, chat rendering), per-figure VLM understanding, citation graph.
- **Frontend** (`web/`) — handle an artifact that has no pages yet (parsing in progress); show parse progress/failure via the existing `/workflows` endpoint. Separate small plan in the `web/` subsystem.

---

## Self-review notes

- **Spec coverage:** §4.1 flow → Tasks 6/7/10; §4.2 components → Tasks 1–8; §4.3 IR → Task 1; §4.4 segmentation → Task 2; §4.5 CSER/images (full-page PNG kept at same keys) → Tasks 3/5; §5 no `parse_status` → honored (status via Temporal, Task 6); §6 idempotency (uuid5) → Tasks 4/5; §7 testing (segmenter unit, PDF parity/quality gate) → Tasks 2/3/9; §8 rollout Phase 0/1 → this plan; Phases 2/3/(B) → out of scope above.
- **Flagged confirmations (open the file, not placeholders):** Docling accessors (Task 3), `ArtifactRepository.get` + `artifact.mime_type`/`storage_location` accessors (Task 5), `ArtifactType` enum member used in tests, `WorkflowStartedResponse` constructor shape (Task 7), `FsspecBlobStore` constructor (Tasks 3/9/11).
