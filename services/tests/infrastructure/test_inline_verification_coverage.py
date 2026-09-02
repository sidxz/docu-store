"""Citation coverage heuristic in InlineVerificationNode._compute_citation_coverage.

Regression coverage for a splitter bug: `re.split(r"(?<=[.!?])\\s+", ...)` tears a
trailing "[n]" citation off into its own fragment, which the `len(s.strip()) > 10`
filter then drops — scoring a visibly cited sentence as uncited. The fix
normalises a trailing citation back inside its sentence, locally to the count,
without touching the answer text shown to the reader.
"""

from infrastructure.chat.nodes.inline_verification import (
    InlineVerificationNode,
    _attach_trailing_citations,
)


def _node() -> InlineVerificationNode:
    return InlineVerificationNode.__new__(InlineVerificationNode)


def test_trailing_citation_after_period_is_counted():
    """'…0.19 uM. [2]' must score as cited, not dropped by the length filter."""
    node = _node()
    answer = "The IC50 of TAM16 against Pks13 is 0.19 uM. [2]"

    coverage = node._compute_citation_coverage(answer)

    assert coverage["ratio"] == 1.0
    assert coverage["factual_sentences"] == 1
    assert coverage["cited_sentences"] == 1


def test_deep_research_style_citation_inside_sentence_is_untouched():
    """Protects the internal-docs (Deep Research) pipeline.

    Deep Research cites *inside* the sentence, before the period (e.g. "...is
    0.19 uM [2]."), and its live-measured coverage (24/25 = 96%) is the sole
    justification for touching this shared file. The normalisation must be a
    complete no-op for this style: same string in, same string out, and the
    computed ratio must not move. If this test ever fails, the fix has
    regressed the product's primary surface — stop and do not proceed.
    """
    answer = "The IC50 of TAM16 against Pks13 is 0.19 uM [2]."

    assert _attach_trailing_citations(answer) == answer

    node = _node()
    coverage = node._compute_citation_coverage(answer)
    assert coverage["ratio"] == 1.0
    assert coverage["cited_sentences"] == 1
    assert coverage["factual_sentences"] == 1


def test_multiple_adjacent_trailing_markers_are_counted():
    node = _node()
    answer = "Compound 44 showed a MIC of 0.07 uM. [1][3]"

    coverage = node._compute_citation_coverage(answer)

    assert coverage["ratio"] == 1.0
    assert coverage["cited_sentences"] == 1


def test_comma_list_trailing_citation_is_counted():
    """CITATION_RE accepts comma-separated marker lists like [1, 2]."""
    node = _node()
    answer = "Compound 44 showed a MIC of 0.07 uM. [1, 2]"

    coverage = node._compute_citation_coverage(answer)

    assert coverage["ratio"] == 1.0
    assert coverage["cited_sentences"] == 1


def test_multi_sentence_answer_each_trailing_its_own_citation():
    node = _node()
    answer = "Page 3 reports a yield of 82%. [7]  A second run reported 79%. [8]"

    coverage = node._compute_citation_coverage(answer)

    assert coverage["ratio"] == 1.0
    assert coverage["factual_sentences"] == 2
    assert coverage["cited_sentences"] == 2


def test_no_citations_at_all_still_scores_zero():
    """The fix must not manufacture coverage where none exists."""
    node = _node()
    answer = "The IC50 of TAM16 against Pks13 is 0.19 uM. It was measured in triplicate."

    coverage = node._compute_citation_coverage(answer)

    assert coverage["ratio"] == 0.0
    assert coverage["cited_sentences"] == 0
    assert coverage["factual_sentences"] == 2


def test_a_citation_after_an_abbreviation_does_not_manufacture_coverage():
    """The period in "e.g." is not a sentence boundary.

    Reattaching across it would bind the citation to a claim it does not
    support and report the sentence as cited when it is not.
    """
    node = _node()
    answer = "The IC50 was 0.19 uM, e.g. [1] in DMSO buffer."

    assert node._compute_citation_coverage(answer)["ratio"] == 0.0


def test_an_abbreviation_before_a_real_sentence_end_is_left_alone():
    node = _node()
    answer = "See Fig. 3. [2] for the dose curve; the compound showed activity."

    assert node._compute_citation_coverage(answer)["ratio"] == 1.0


def test_a_markdown_header_after_a_citation_is_not_pulled_in():
    answer = "The yield was measured at 82%. [3]\n\n## Next section"

    assert "## Next section" in _attach_trailing_citations(answer)
