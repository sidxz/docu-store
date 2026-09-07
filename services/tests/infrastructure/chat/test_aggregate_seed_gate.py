"""The aggregate flag ungates the unfiltered seed, and nothing else.

The regression these guard against: an aggregation question ("how many compounds
clear this threshold") is classified factual, carries an NER filter, and so runs
filtered-only -- excluding the very rows being counted. Measured on the
benchmark, 28 of the aggregation sheet's 40 failures work that way, and 17 of the
31 filtered-only failures across two sheets retrieved zero sources.

The fix must stay surgical. Force-injection keeps the model's own searches
entity-scoped, which is what preserves compound/target binding when the planner
flags a question wrongly -- a global CHAT_FACTUAL_SKIP_UNFILTERED=false was
already rejected for breaking exactly that.
"""

from __future__ import annotations

import inspect

from infrastructure.chat.models import QueryPlan
from infrastructure.chat.nodes import agentic_retrieval


def _plan(**kw) -> QueryPlan:
    base = {
        "query_type": "factual",
        "reformulated_query": "q",
        "search_strategy": "hierarchical",
        "summary": "s",
    }
    return QueryPlan(**{**base, **kw})


def test_aggregate_defaults_false() -> None:
    """A planner that omits the key, or fails outright, keeps today's behaviour."""
    assert _plan().aggregate is False
    # Pydantic ignores an unknown key rather than raising, so an older prompt
    # still parses; and the module's own fallback plan must not opt in.
    assert agentic_retrieval is not None
    from infrastructure.chat.nodes.query_planning import _default_llm_plan

    assert _default_llm_plan("anything").aggregate is False


def test_aggregate_is_independent_of_query_type() -> None:
    """It is a second fact about the question, not a sixth query_type value.

    A count is factual AND an aggregate; an agreement check is comparative AND an
    aggregate. Measured on the benchmark, of 95 flagged questions 58 were factual
    and 34 comparative -- one field cannot carry both.
    """
    assert _plan(query_type="factual", aggregate=True).query_type == "factual"
    assert _plan(query_type="comparative", aggregate=True).query_type == "comparative"


def test_seed_gate_reads_the_flag_and_force_injection_does_not() -> None:
    """The source-level invariant: exactly one of the two gates consults it.

    Behavioural, not cosmetic. `skip_unfiltered_seed` controls two things -- the
    unfiltered seed search, and force-injecting entity filters into every
    subsequent tool call the model makes. Binding breaks through the second. If a
    later edit adds `plan.aggregate` to the force-injection site, this fails.
    """
    src = inspect.getsource(agentic_retrieval)

    seed_gate = "if skip_unfiltered_seed and not plan.aggregate:"
    assert seed_gate in src, "the unfiltered seed is no longer ungated for aggregates"

    # Every place the flag is consulted, and how many there are.
    gates = [ln.strip() for ln in src.splitlines()
             if "skip_unfiltered_seed" in ln and ln.strip().startswith("if ")]
    assert gates.count(seed_gate) == 1, gates
    assert len(gates) == 2, f"expected exactly the seed gate and the force-inject gate: {gates}"

    force_inject = [g for g in gates if g != seed_gate]
    assert force_inject == ["if skip_unfiltered_seed:"], (
        f"force-injection must NOT consult plan.aggregate; found {force_inject}"
    )


def test_planner_prompt_declares_the_field_and_stays_generic() -> None:
    """The prompt must ask for the key, and must not be tuned to the benchmark.

    The higher-scoring 284-word variant was discarded for quoting benchmark
    question HARD-0066 verbatim; a description tuned to benchmark rows teaches the
    planner nothing that transfers. Keep this assertion.
    """
    import pathlib

    yaml_path = (
        pathlib.Path(agentic_retrieval.__file__).parents[3]
        / "infrastructure/llm/default_prompts/chat_query_planning.yaml"
    )
    text = yaml_path.read_text(encoding="utf-8")

    assert '"aggregate": false,' in text, "the JSON block does not request the key"
    assert '- "aggregate": decide between two readings' in text, "guideline missing"

    # A sibling of - "query_type", never nested among its values: nesting it
    # contradicts the guideline's own "INDEPENDENT of query_type" sentence.
    assert '\n  - "aggregate":' in text
    assert '\n    - "aggregate":' not in text, "guideline is nested under query_type"

    for leak in ("HARD-", "CHEMBL", "TCA1", "PBTZ169", "MIC90", "deck"):
        assert leak not in text.split('- "aggregate":')[1].split("\n  - ")[0], (
            f"benchmark-specific token {leak!r} leaked into the guideline"
        )
