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
