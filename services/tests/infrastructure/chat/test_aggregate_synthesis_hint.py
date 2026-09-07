"""The enumeration hint reaches synthesis only for aggregate plans.

The regression this guards: 16 benchmark questions had EVERY gold slide in the
assembled context and still answered wrongly -- 11 of the 14 multi-slide cases
cited fewer sources than the answer's population spans, one with 8 gold slides in
front of it citing 1. That is a synthesis failure, not a retrieval one, so it
needs its own signal and its own check.

Why a context note and not a system prompt: swapping the system prompt would take
the citation discipline and the don't-guess rules with it, and those hold the 117
abstain questions at 96% correctly declined.
"""

from __future__ import annotations

from infrastructure.chat.models import ContextMetadata, QueryPlan
from infrastructure.chat.nodes.adaptive_synthesis import (
    _SCAN_HINT,
    _SYSTEM_PROMPT_MAP,
    AdaptiveSynthesisNode,
)


class _FakeLLM:
    async def complete(self, prompt, **kw):  # noqa: ANN001, ANN003, ARG002
        return "PLAN"


class _FakePrompts:
    async def render_prompt(self, name, **kw):  # noqa: ANN001, ANN003, ARG002
        return "SYS"


def _node() -> AdaptiveSynthesisNode:
    return AdaptiveSynthesisNode(_FakeLLM(), _FakePrompts())


def _plan(**kw) -> QueryPlan:
    base = {
        "query_type": "factual",
        "reformulated_query": "q",
        "search_strategy": "hierarchical",
        "summary": "s",
    }
    return QueryPlan(**{**base, **kw})


def _meta() -> ContextMetadata:
    return ContextMetadata(
        total_sources=8, high_relevance_count=4, avg_relevance_score=0.8,
        unique_artifacts=2, has_summaries=False,
    )


def test_hint_absent_unless_flagged() -> None:
    """Every unflagged question must get byte-identical notes to today."""
    hints = _node()._build_context_hints(_meta(), _plan())
    assert _SCAN_HINT not in hints
    assert "work through all of them" not in hints


def test_hint_present_when_flagged() -> None:
    hints = _node()._build_context_hints(_meta(), _plan(aggregate=True))
    assert _SCAN_HINT in hints


def test_hint_does_not_displace_the_other_notes() -> None:
    """It is appended, not substituted: the metadata notes still get through."""
    meta = ContextMetadata(
        total_sources=9, high_relevance_count=0, avg_relevance_score=0.3,
        unique_artifacts=7, has_summaries=True,
    )
    plain = _node()._build_context_hints(meta, _plan())
    flagged = _node()._build_context_hints(meta, _plan(aggregate=True))
    assert plain, "expected the metadata notes to fire on this ContextMetadata"
    for note in plain.split(". "):
        if note.strip():
            assert note.strip().rstrip(".") in flagged
    # Appended last on purpose: the notes above it are the conservatism guards,
    # and framing those with "enumerate and state a result" is backwards for the
    # population this change must not break.
    assert flagged.endswith(_SCAN_HINT), "the hint must come after the conservatism notes"


def test_hint_tells_the_model_to_decline_not_merely_to_skip_a_source() -> None:
    """The first draft said "if a source has no matching row, leave it out".

    That governs ONE non-matching source and never the case where nothing
    matches -- which is the case 117 abstain questions live in, at 96% correctly
    declined. Abstain questions are disproportionately aggregate-SHAPED ("how
    many X meet Y" where Y is unreported), so the hint reaches them above the
    classifier's base error rate.
    """
    low = _SCAN_HINT.lower()
    assert "do not report it" in low and "no number" in low, (
        "the hint must say what to do when NOTHING matches, not just when one source does not"
    )
    for banned in ("estimate", "infer", "assume", "approximate"):
        assert banned not in low, f"{banned!r} invites a fabricated count"


def test_hint_blocks_pooling_across_incomparable_measurements() -> None:
    """Guards the MISCLASSIFIED lookup, not the intended target.

    The classifier has a ~12% false-positive rate, so single-table superlatives
    ("which compound had the lowest X") will receive this hint. Without a
    comparability clause, "every matching row" licenses pooling values across
    assays and units before taking a minimum -- turning a correct single-table
    answer into a wrong cross-table one that still carries a valid citation.
    """
    low = _SCAN_HINT.lower()
    assert "never pool" in low
    assert "assays" in low or "units" in low


def test_hint_is_silent_when_there_is_nothing_to_count() -> None:
    """With an empty context the note would open a counting frame over nothing,
    which is the shape of a fabricated answer. sources_text is literally
    "No relevant sources found." there, so staying quiet costs nothing."""
    empty = ContextMetadata(
        total_sources=0, high_relevance_count=0, avg_relevance_score=0.0,
        unique_artifacts=0, has_summaries=False,
    )
    assert _SCAN_HINT not in _node()._build_context_hints(empty, _plan(aggregate=True))


def test_flagging_does_not_change_the_system_prompt() -> None:
    """The whole point of the boolean: query_type is untouched, so the factual
    system prompt is selected exactly as before. A sixth query_type value would
    have rerouted 38 currently-passing questions onto a different prompt."""
    for qt in ("factual", "comparative", "exploratory", "compound", "follow_up"):
        plain = _SYSTEM_PROMPT_MAP.get(_plan(query_type=qt).query_type)
        flagged = _SYSTEM_PROMPT_MAP.get(_plan(query_type=qt, aggregate=True).query_type)
        assert plain == flagged is not None, qt


def test_answer_plan_agrees_with_the_hint_on_the_reasoning_path() -> None:
    """The plan string lands in "follow this closely" -- above the context notes.

    When synthesis reasoning is on (the benchmark pins CHAT_SYNTHESIS_REASONING),
    the separate planning call is skipped and a constant is used instead. The
    default constant says "map each source to the part of the question it
    answers" -- one-source-one-fact framing, i.e. the exact failure being fixed,
    stated with more authority than the hint. If it does not branch, the hint
    argues with the prompt and loses.
    """
    import inspect

    from infrastructure.chat.nodes import adaptive_synthesis

    src = inspect.getsource(adaptive_synthesis.AdaptiveSynthesisNode.run)
    assert "map each source to the part of the question" in src, "default plan moved"
    head = src[: src.index("map each source to the part of the question")]
    assert "plan.aggregate" in head, (
        "the hardcoded answer_plan must branch on plan.aggregate; otherwise the "
        "highest-authority slot in the prompt contradicts the hint"
    )
    assert "Enumerate every matching row" in src
