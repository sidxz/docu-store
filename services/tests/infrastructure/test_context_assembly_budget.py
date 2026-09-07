"""Budget and tiering rules for the internal-docs context assembler.

Three properties, each of which was broken and none of which had a test:
one long source must not shut out the shorter ones behind it; what a source is
charged must equal what it emits; and the rerank thresholds must be on the same
scale as the scores they are compared against.
"""

from uuid import uuid4

from infrastructure.chat.nodes import context_assembly as ca
from infrastructure.chat.models import RetrievalResult

ARTIFACT = uuid4()


def _result(text: str, *, rerank=None, sim=0.5, source="tool:q") -> RetrievalResult:
    return RetrievalResult(
        source_type="chunk",
        artifact_id=ARTIFACT,
        page_id=uuid4(),
        page_index=1,
        expanded_text=text,
        matched_text=text,
        similarity_score=sim,
        rerank_score=rerank,
        query_source=source,
    )


def test_an_oversized_source_is_skipped_not_a_wall():
    """`break` let one long source drop every shorter one ranked below it."""
    node = ca.ContextAssemblyNode()
    huge = _result("H" * 5000, rerank=0.99)
    small = _result("small", rerank=0.98)

    selected, chars = node._apply_budget([huge, small], [], [], budget=1000)

    assert small in selected
    assert huge not in selected
    assert chars == len("small")


def test_charged_length_equals_emitted_length():
    """The budget and the prompt now read tier and cap from one helper."""
    node = ca.ContextAssemblyNode()
    results = [
        _result("A" * 9000, rerank=0.99),      # high, capped
        _result("B" * 4000, rerank=0.2),       # medium, capped
        _result("C" * 4000, rerank=0.001),     # low, capped + ellipsis
    ]
    selected, chars = node._apply_budget(*node._tier_results(results), budget=100_000)

    assert len(selected) == 3
    _citations, formatted, _meta = node.run(results)
    assert chars == sum(len(node._display_text(r)) for r in selected)
    for r in selected:
        assert node._display_text(r) in formatted


def test_high_tier_is_capped_so_one_page_cannot_eat_the_budget():
    node = ca.ContextAssemblyNode()
    assert len(node._display_text(_result("A" * 9000, rerank=0.99))) == ca._HIGH_CHARS


def test_structured_tool_output_is_never_truncated():
    """Bioactivity and structure stay whole: a half-delivered assay table reads
    as 'no such measurement' rather than as elided."""
    node = ca.ContextAssemblyNode()
    table = "row\n" * 3000
    r = _result(table, sim=0.9, source="tool_bioactivity:compound-1")
    assert node._tier_of(r) == "high"
    assert node._display_text(r) == table


def test_bioactivity_still_gets_the_budget_first():
    node = ca.ContextAssemblyNode()
    bio = _result("bio", sim=0.9, source="tool_bioactivity:x")
    page = _result("P" * 900, rerank=0.99)
    selected, _ = node._apply_budget([page, bio], [], [], budget=950)
    assert selected == [bio, page] or selected == [bio]
    assert bio in selected


def test_rerank_thresholds_are_on_the_probability_scale():
    """Scores arrive squashed, so the cut-points must be probabilities.

    Under the old logit-shaped 0.7/0.4 a well-matched passage scoring 0.89 would
    have been tiered LOW and cut to 200 characters.
    """
    node = ca.ContextAssemblyNode()
    assert 0.0 < ca._HIGH_RERANK < 1.0
    assert 0.0 < ca._MED_RERANK < ca._HIGH_RERANK
    assert node._tier_of(_result("t", rerank=0.89)) == "high"
    assert node._tier_of(_result("t", rerank=0.30)) == "medium"
    assert node._tier_of(_result("t", rerank=0.01)) == "low"


def test_cosine_scored_sources_keep_their_own_cut_points():
    """A page fetch has no rerank score and must stay HIGH on its 1.0 sentinel."""
    node = ca.ContextAssemblyNode()
    fetch = _result("text", sim=1.0, source="tool_page_content")
    assert fetch.rerank_score is None
    assert node._tier_of(fetch) == "high"
    assert node._tier_of(_result("t", sim=0.7)) == "medium"


def test_carried_forward_stays_medium_regardless_of_score():
    node = ca.ContextAssemblyNode()
    assert node._tier_of(_result("t", sim=0.99, source="carried_forward")) == "medium"


def test_every_tier_marks_its_truncation():
    """A cut value must not read as a whole one.

    MEDIUM and HIGH used to truncate silently, and they are the tiers that carry
    tables: a page cut mid-number handed the model ``Rifampicin ... 0.`` with
    nothing to say that was half of 0.20.
    """
    node = ca.ContextAssemblyNode()
    for text, kw, cap in (
        ("A" * 9000, {"rerank": 0.99}, ca._HIGH_CHARS),
        ("A" * 9000, {"rerank": 0.1}, ca._MEDIUM_CHARS),
        ("A" * 9000, {"rerank": 0.001}, ca._LOW_CHARS),
    ):
        out = node._display_text(_result(text, **kw))
        assert out.endswith("..."), kw
        assert len(out) == cap, kw  # the marker fits inside the cap, not past it


def test_text_that_fits_is_left_alone():
    node = ca.ContextAssemblyNode()
    short = "Rifampicin - CHEMBL374478 - 0.20 uM"
    assert node._display_text(_result(short, rerank=0.99)) == short
    assert node._display_text(_result(short, rerank=0.001)) == short


def test_a_source_is_charged_what_it_emits():
    """The ellipsis is inside the cap, so budget arithmetic needs no allowance."""
    node = ca.ContextAssemblyNode()
    r = _result("A" * 9000, rerank=0.1)
    selected, used = node._apply_budget([], [r], [], budget=ca._MEDIUM_CHARS)
    assert selected == [r]
    assert used == len(node._display_text(r)) == ca._MEDIUM_CHARS


TABLE = "# MIC against H37Rv\n\n| cpd | MIC |\n| --- | --- |\n| 8k | 0.06 |\n" + "| 8t | 0.03 |\n" * 400
PROSE = "The series was profiled against H37Rv. " * 60


def test_a_medium_page_holding_a_table_gets_the_high_cap():
    """Rows past a cut read as "no such measurement", so tables are not clipped
    to 1000 characters just because a prose chunk outscored them."""
    node = ca.ContextAssemblyNode()
    assert len(TABLE) > ca._HIGH_CHARS
    assert len(node._display_text(_result(TABLE, rerank=0.1))) == ca._HIGH_CHARS


def test_prose_keeps_the_medium_cap():
    node = ca.ContextAssemblyNode()
    assert len(PROSE) > ca._MEDIUM_CHARS
    assert len(node._display_text(_result(PROSE, rerank=0.1))) == ca._MEDIUM_CHARS


def test_a_table_page_that_fits_is_untouched():
    node = ca.ContextAssemblyNode()
    small = "| cpd | MIC |\n| --- | --- |\n| 8t | 0.03 |"
    assert node._display_text(_result(small, rerank=0.1)) == small


def test_tables_are_still_capped_so_one_page_cannot_eat_the_budget():
    """Promoted, not exempt: the HIGH cap still bounds what a table can spend."""
    node = ca.ContextAssemblyNode()
    huge = _result("| a | b |\n" * 5000, rerank=0.1)
    selected, used = node._apply_budget([], [huge], [], budget=ca._HIGH_CHARS)
    assert selected == [huge]
    assert used == ca._HIGH_CHARS


def test_table_detection_needs_a_pipe_row_not_just_a_pipe():
    node = ca.ContextAssemblyNode()
    piped = "Use grep foo | wc -l to count. " * 60
    assert len(node._display_text(_result(piped, rerank=0.1))) == ca._MEDIUM_CHARS
