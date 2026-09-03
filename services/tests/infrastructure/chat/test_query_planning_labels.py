"""The planner's entity labels, and the ablation that is supposed to remove them."""

import pytest

from application.ports.ner_extractor import NEREntity
from application.ports.structured_extractor import ExtractedField
from infrastructure.chat.nodes.query_planning import _AUTHOR_SCHEMA, QueryPlanningNode


def test_author_schema_offers_a_non_author_label():
    """A one-label schema forces assignment; GLiNER2 has no "none of the above".

    With author_name as the only option, the paper title in 'Working from "Making
    MRSA sensitive again" alone...' came back as an author at 0.814 -- above every
    usable threshold. The competing label is what lets the model say "not a
    person": offered document_title, it puts the same span there at 0.999 and
    returns no author at all.
    """
    labels = [f.split("::")[0] for f in _AUTHOR_SCHEMA]   # all the adapter passes on
    assert "author_name" in labels
    assert len(labels) > 1, "a single-label schema has nothing to reject a title with"
    assert "document_title" in labels


class _Fake:
    """Stands in for whichever collaborator; raising is a supported path."""

    def __init__(self, result=None):
        self._result = result

    async def extract(self, text, schema=None, *, threshold=0.3):
        return self._result

    async def get_prompt(self, *a, **k):
        raise RuntimeError("no prompt repo in this test")


@pytest.mark.asyncio
async def test_ablation_clears_author_mentions_too(monkeypatch):
    """CHAT_CLEAR_NER_FILTERS must leave retrieval with no tag filter at all.

    Retrieval builds its tags from the entity texts *plus* the author mentions, so
    clearing only the entities left the "unconstrained" arm filtered by author. On
    a question naming a paper that meant tags=['Making MRSA sensitive again'], a
    tag no chunk carries -- the arm measured zero-recall search, not unfiltered
    search, and every number it produced was wrong.
    """
    from infrastructure.config import settings

    monkeypatch.setattr(settings, "chat_clear_ner_filters", True)

    node = QueryPlanningNode(
        llm_client=_Fake(),
        prompt_repository=_Fake(),
        ner_extractor=_Fake([NEREntity(text="MRSA", entity_type="gene_name")]),
        structured_extractor=_Fake([ExtractedField(name="author_name", value="Chang", score=0.9)]),
    )
    plan, _ = await node.run("what did Chang report about MRSA?", [])

    assert plan.ner_entity_filters == []
    assert plan.author_mentions == [], "author mentions still become a tag filter"
