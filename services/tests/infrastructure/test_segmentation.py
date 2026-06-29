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
