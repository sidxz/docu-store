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
