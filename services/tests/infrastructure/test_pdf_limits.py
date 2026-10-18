"""PDFs are bounded before Docling renders them at 4x (a page is a pixel budget)."""

import fitz
import pytest

from infrastructure.file_services.docling_parser import DoclingParser


def _pdf(path, pages=1, size=(612, 792), **save_kw):
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=size[0], height=size[1])
    doc.save(path, **save_kw)
    return path


def test_rejects_page_larger_than_a0(tmp_path):
    with pytest.raises(ValueError, match="page"):
        DoclingParser(blob_store=None).parse_path(_pdf(tmp_path / "x.pdf", size=(20000, 20000)))


def test_rejects_too_many_pages(tmp_path):
    with pytest.raises(ValueError, match="pages"):
        DoclingParser(blob_store=None).parse_path(_pdf(tmp_path / "x.pdf", pages=2001))


def test_rejects_password_protected(tmp_path):
    path = _pdf(
        tmp_path / "x.pdf", encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o"
    )
    with pytest.raises(ValueError, match="password"):
        DoclingParser(blob_store=None).parse_path(path)
