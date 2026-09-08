"""The aggregate flag on a query plan.

An aggregation question ("how many compounds clear this threshold") is
classified factual and carries an NER filter, so it used to run filtered-only,
excluding the very rows being counted. The flag lets the unfiltered seed run
for such questions without changing anything else about the plan.
"""

from __future__ import annotations

from infrastructure.chat.models import QueryPlan
from infrastructure.chat.nodes.query_planning import _default_llm_plan


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
    assert _default_llm_plan("anything").aggregate is False


def test_aggregate_is_independent_of_query_type() -> None:
    """A second fact about the question, not another query_type value.

    A count is factual AND an aggregate; an agreement check is comparative AND
    an aggregate.
    """
    assert _plan(query_type="factual", aggregate=True).query_type == "factual"
    assert _plan(query_type="comparative", aggregate=True).query_type == "comparative"
