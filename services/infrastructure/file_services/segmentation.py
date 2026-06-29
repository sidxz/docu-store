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
    mime_type: str,  # noqa: ARG001 — Phase 2 dispatches on mime_type
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

    return [Segment(index=p.index, text=linearize_blocks(by_page.get(p.index, []))) for p in pages]
