from application.dtos.parsed_document import Block
from infrastructure.text_chunkers.block_aware_chunker import (
    BlockChunk, chunk_blocks, chunk_payload, scope_table_entities,
)


def test_scope_keeps_local_entity_drops_remote():
    candidates = [("PptT", "target"), ("Rho", "target"), ("CmpdX", "compound_name")]
    local = "| Cmpd | IC50 |\n| CmpdX | 5 nM |\n\n*Table 1. PptT inhibition*"
    out = scope_table_entities(candidates, local)
    assert out["tag_normalized"] == ["pptt", "cmpdx"]   # PptT (caption) + CmpdX (cell)
    assert "rho" not in out["tag_normalized"]            # Rho not in the table's own text
    assert out["entity_types"] == ["compound_name", "target"]


def test_scope_word_boundary_not_substring():
    out = scope_table_entities([("Rho", "target")], "rhodamine staining only")
    assert out["tag_normalized"] == []                   # 'rho' must not match 'rhodamine'


def test_scope_section_heading_contributes():
    # local_text = table markdown + " " + " ".join(section_path)
    local = "| Cmpd | IC50 |\n| CmpdX | 5 nM | Rho inhibitors"
    out = scope_table_entities([("Rho", "target")], local)
    assert out["tag_normalized"] == ["rho"]


def test_scope_empty_when_no_local_match():
    out = scope_table_entities(
        [("PptT", "target"), ("Rho", "target")],
        "| Cmpd | IC50 |\n| CmpdX | 5 nM |",
    )
    assert out == {"tags": [], "tag_normalized": [], "entity_types": []}


def test_scope_ignores_blank_candidate():
    out = scope_table_entities([("", "target")], "anything here")
    assert out["tag_normalized"] == []                   # blank tag never matches


def test_chunk_payload_shape():
    c = BlockChunk(text="t", block_type="table", section_path=["Results", "Assay"],
                   is_table=True, is_figure=False, caption="Table 1")
    p = chunk_payload(c)
    assert p == {
        "block_type": "table", "is_table": True, "is_figure": False,
        "section_path": ["Results", "Assay"],
        "section_path_normalized": ["results", "assay"],
        "caption": "Table 1",
    }
    # caption omitted when absent
    assert "caption" not in chunk_payload(BlockChunk(text="t", block_type="paragraph"))


def test_table_is_one_intact_chunk():
    blocks = [Block(type="table", rows=[["Cmpd", "IC50"], ["X", "5 nM"]], caption="Table 1")]
    chunks = chunk_blocks(blocks, max_chars=1000)
    assert len(chunks) == 1
    assert chunks[0].is_table is True
    assert "| Cmpd | IC50 |" in chunks[0].text
    assert "| X | 5 nM |" in chunks[0].text  # not split across chunks
    assert chunks[0].caption == "Table 1"


def test_heading_binds_to_following_content():
    blocks = [
        Block(type="heading", text="Methods", level=1, section_path=[]),
        Block(type="paragraph", text="We did X.", section_path=["Methods"]),
        Block(type="paragraph", text="Then Y.", section_path=["Methods"]),
    ]
    chunks = chunk_blocks(blocks, max_chars=1000)
    assert len(chunks) == 1
    assert "# Methods" in chunks[0].text
    assert "We did X." in chunks[0].text and "Then Y." in chunks[0].text
    assert chunks[0].section_path == []  # chunk's path = heading's own path


def test_new_heading_starts_new_chunk():
    blocks = [
        Block(type="heading", text="A", level=1),
        Block(type="paragraph", text="aaa"),
        Block(type="heading", text="B", level=1),
        Block(type="paragraph", text="bbb"),
    ]
    chunks = chunk_blocks(blocks, max_chars=1000)
    assert len(chunks) == 2


def test_figure_is_its_own_chunk_with_caption():
    blocks = [Block(type="figure", caption="Fig 2: gel", section_path=["Results"])]
    chunks = chunk_blocks(blocks, max_chars=1000)
    assert len(chunks) == 1
    assert chunks[0].is_figure is True
    assert chunks[0].caption == "Fig 2: gel"
    assert "[Figure: Fig 2: gel]" in chunks[0].text
    assert chunks[0].section_path == ["Results"]


def test_size_cap_splits_prose_at_block_boundary():
    blocks = [Block(type="paragraph", text="x" * 400) for _ in range(4)]  # 1600 chars
    chunks = chunk_blocks(blocks, max_chars=1000)
    assert len(chunks) == 2  # 2+2 paragraphs, never mid-paragraph
    assert all(not c.is_table and not c.is_figure for c in chunks)


def test_oversized_table_splits_by_rows_repeating_header():
    body = [[f"C{i}", f"{i} nM"] for i in range(60)]
    blocks = [Block(type="table", rows=[["Cmpd", "IC50"], *body], caption="Big")]
    chunks = chunk_blocks(blocks, max_chars=300)
    assert len(chunks) > 1
    assert all(c.is_table for c in chunks)
    assert all("| Cmpd | IC50 |" in c.text for c in chunks)  # header repeated


def test_oversized_single_paragraph_char_splits():
    blocks = [Block(type="paragraph", text="y" * 2500)]
    chunks = chunk_blocks(blocks, max_chars=1000)
    assert len(chunks) == 3
    assert all(len(c.text) <= 1000 for c in chunks)
