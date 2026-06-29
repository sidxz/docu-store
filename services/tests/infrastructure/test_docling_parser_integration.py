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
