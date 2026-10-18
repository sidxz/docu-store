"""Child functions must be module-level so multiprocessing spawn can pickle them."""

import os

import fitz

from infrastructure.file_services.font_title_extractor import FontTitleExtractor


def _crashing_spans(_path, _page_index):
    os._exit(1)  # a native MuPDF crash: no result, no exception


def test_extracts_largest_font_as_title(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Kinase Inhibitor Review", fontsize=28)
    page.insert_text((72, 200), "body text in a much smaller font", fontsize=10)
    doc.save(tmp_path / "x.pdf")

    candidate = FontTitleExtractor().extract_title(tmp_path / "x.pdf")

    assert candidate.title == "Kinase Inhibitor Review"


def test_parser_crash_returns_none_instead_of_killing_the_worker(tmp_path):
    (tmp_path / "x.pdf").write_bytes(b"%PDF-1.4")

    assert FontTitleExtractor(spans_fn=_crashing_spans).extract_title(tmp_path / "x.pdf") is None
