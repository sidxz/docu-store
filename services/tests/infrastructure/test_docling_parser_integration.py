from __future__ import annotations

import io
from pathlib import Path

import pytest

from infrastructure.blob_stores.fsspec_blob_store import FsspecBlobStore
from infrastructure.file_services.docling_parser import DoclingParser


@pytest.mark.integration
def test_docling_parses_pdf_into_pages_and_text(tmp_path):
    pdf = Path("tests/fixtures/sample_two_page.pdf").read_bytes()
    store = FsspecBlobStore(base_url=f"file://{tmp_path}")
    store.put_stream("artifacts/x/source.pdf", io.BytesIO(pdf), mime_type="application/pdf")

    result = DoclingParser(blob_store=store).parse("artifacts/x/source.pdf")

    assert result.document.source_mime == "application/pdf"
    assert len(result.pages) >= 1
    assert result.pages[0].png  # non-empty PNG bytes
    assert any(b.text.strip() for b in result.document.blocks)
    # page-index invariant: Docling is 1-based, we must output 0-based
    assert len(result.pages) == 2
    assert result.pages[0].index == 0
    assert result.pages[1].index == 1
    assert any(b.source_page_index is not None for b in result.document.blocks)


def test_docling_refuses_non_pdf_input(tmp_path):
    # Docling routes by extension; only its PDF backend may ever run.
    page = tmp_path / "page.html"
    page.write_text("<html><body><h1>Hi</h1><p>not a pdf</p></body></html>")

    with pytest.raises(Exception):  # noqa: B017, PT011 — docling's error type varies by version
        DoclingParser(blob_store=None)._get_converter().convert(str(page))
