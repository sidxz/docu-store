"""Scoring papers against the claim in the question, not for sentiment.

Sentiment is uniform: nearly every abstract is positive about its own result, so
a sentiment timeline is one flat band forever. Stance is not, and the MmpL3
proton-motive-force question is the worked example — the field's answer visibly
turns in 2019.
"""

from __future__ import annotations

import json

import pytest

from infrastructure.chat.stance_classifier import (
    STANCE_LABELS,
    classify_stance,
)
from infrastructure.literature.europe_pmc import LiteratureHit


class _StubLLM:
    """Returns one canned JSON payload and records the prompt it was given."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[str] = []

    async def complete(self, prompt: str, **kwargs) -> str:
        self.calls.append(prompt)
        return json.dumps(self.payload)


def _hit(external_id: str, title: str, abstract: str, year: int) -> LiteratureHit:
    return LiteratureHit(
        external_id=external_id,
        source="MED",
        title=title,
        abstract=abstract,
        year=year,
    )


HITS = [
    _hit("a", "Novel acetamide targets MmpL3 by PMF disruption", "…indirectly…", 2018),
    _hit("b", "Direct inhibition of MmpL3", "…directly interact with MmpL3…", 2019),
    _hit("c", "Proton transfer activity of reconstituted MmpL3", "…physiology…", 2022),
]


async def test_every_paper_gets_exactly_one_label_from_the_fixed_set():
    llm = _StubLLM(
        {
            "verdicts": [
                {"id": "a", "label": "supports", "evidence": "indirectly, by PMF disruption"},
                {"id": "b", "label": "refutes", "evidence": "directly interact with MmpL3"},
                {"id": "c", "label": "none", "evidence": "describes transport physiology"},
            ],
        },
    )
    verdicts = await classify_stance(llm, "MmpL3 inhibitors act by disrupting PMF", HITS)

    assert len(verdicts) == len(HITS)
    assert {v.label for v in verdicts} <= set(STANCE_LABELS)
    assert verdicts[1].label == "refutes"


async def test_all_the_abstracts_go_in_one_call():
    # One call, not one per paper: this is spent against the user's own key.
    llm = _StubLLM({"verdicts": [{"id": h.external_id, "label": "none", "evidence": ""} for h in HITS]})
    await classify_stance(llm, "a claim", HITS)
    assert len(llm.calls) == 1
    for h in HITS:
        assert h.external_id in llm.calls[0]


async def test_every_verdict_carries_the_sentence_that_decided_it():
    # Stance is a judgement. A reader must be able to overrule it, which means
    # seeing what the model read.
    llm = _StubLLM(
        {"verdicts": [{"id": "a", "label": "supports", "evidence": "indirectly, by PMF disruption"}]},
    )
    verdicts = await classify_stance(llm, "a claim", HITS[:1])
    assert verdicts[0].evidence == "indirectly, by PMF disruption"


async def test_a_paper_the_model_skipped_defaults_to_no_position():
    # Never drop a paper silently: an absent verdict must show as "no position",
    # not vanish from the chart and change the totals.
    llm = _StubLLM({"verdicts": [{"id": "a", "label": "supports", "evidence": "x"}]})
    verdicts = await classify_stance(llm, "a claim", HITS)
    assert len(verdicts) == 3
    assert [v.label for v in verdicts[1:]] == ["none", "none"]


async def test_an_unparseable_response_yields_no_verdicts_rather_than_guesses():
    class _Broken(_StubLLM):
        async def complete(self, prompt: str, **kwargs) -> str:
            return "I could not do that."

    verdicts = await classify_stance(_Broken({}), "a claim", HITS)
    assert verdicts == []
