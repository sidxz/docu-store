"""CserPipelineService hands one page to structflo-cser's own PDF path (library-owned rendering)."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest

from infrastructure.blob_stores.fsspec_blob_store import FsspecBlobStore
from infrastructure.cser.cser_pipeline_service import CserPipelineService


class _FakePipeline:
    """Records what it was given; inspects the PDF while it still exists."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def process_pdf(self, pdf_path, **kwargs):  # noqa: ANN001, ANN003
        doc = fitz.open(str(pdf_path))
        self.calls.append(
            {"page_count": doc.page_count, "text": doc[0].get_text().strip(), "kwargs": kwargs},
        )
        doc.close()
        return [[SimpleNamespace(smiles="CCO", label_text="CHEMBL 1 · 7", match_confidence=0.91)]]


@pytest.fixture
def store(tmp_path):  # noqa: ANN001, ANN201
    s = FsspecBlobStore(base_url=f"file://{tmp_path}")
    s.put_stream(
        "artifacts/x/source.pdf",
        io.BytesIO(Path("tests/fixtures/sample_two_page.pdf").read_bytes()),
        mime_type="application/pdf",
    )
    return s


def test_second_page_is_sent_alone_with_library_default_rendering(store) -> None:  # noqa: ANN001
    svc = CserPipelineService(blob_store=store)
    svc._pipeline = _FakePipeline()

    results = svc.extract_compounds_from_pdf_page("artifacts/x/source.pdf", page_index=1)

    call = svc._pipeline.calls[0]
    src = fitz.open("tests/fixtures/sample_two_page.pdf")
    assert call["page_count"] == 1
    assert call["text"] == src[1].get_text().strip()  # the requested page, not page 0
    assert call["kwargs"] == {}  # no dpi override: the library's default is the contract
    assert [(r.smiles, r.label_text, r.match_confidence) for r in results] == [
        ("CCO", "CHEMBL 1 · 7", 0.91),
    ]


def test_no_pairs_maps_to_empty_list(store) -> None:  # noqa: ANN001
    svc = CserPipelineService(blob_store=store)
    fake = _FakePipeline()
    fake.process_pdf = lambda pdf_path, **kw: [[]]  # noqa: ARG005
    svc._pipeline = fake
    assert svc.extract_compounds_from_pdf_page("artifacts/x/source.pdf", page_index=0) == []
