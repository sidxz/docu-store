from application.dtos.parsed_document import (
    Block,
    ParsedDocument,
    assign_section_paths,
    linearize_blocks,
)


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


def test_section_path_nests_headings_and_content():
    blocks = [
        Block(type="heading", text="Results", level=1),
        Block(type="heading", text="Assay", level=2),
        Block(type="paragraph", text="IC50 was 2 nM."),
        Block(type="heading", text="Discussion", level=1),
        Block(type="paragraph", text="We conclude X."),
    ]
    assign_section_paths(blocks)
    assert blocks[0].section_path == []                       # h1: no ancestors
    assert blocks[1].section_path == ["Results"]              # h2 under h1
    assert blocks[2].section_path == ["Results", "Assay"]     # content under h1>h2
    assert blocks[3].section_path == []                       # h1 pops back to root
    assert blocks[4].section_path == ["Discussion"]


def test_section_path_handles_no_level_as_level_one():
    blocks = [
        Block(type="heading", text="Title"),       # level None -> treated as 1
        Block(type="paragraph", text="body"),
    ]
    assign_section_paths(blocks)
    assert blocks[1].section_path == ["Title"]


def test_linearize_already_renders_caption_and_level():
    # Guards the Phase A premise: linearize consumes fields A2 will populate.
    out = linearize_blocks([
        Block(type="heading", text="Methods", level=2),
        Block(type="figure", caption="Figure 3: aminopyrimidine SAR vs hERG"),
        Block(type="table", rows=[["Cmpd", "IC50"], ["X", "5 nM"]], caption="Table 1: potency"),
    ])
    assert "## Methods" in out
    assert "[Figure: Figure 3: aminopyrimidine SAR vs hERG]" in out
    assert "*Table 1: potency*" in out
