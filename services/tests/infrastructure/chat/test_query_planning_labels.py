"""The ablation flag that is supposed to remove the planner's entity filters."""

from uuid import uuid4
import pytest

from application.ports.ner_extractor import NEREntity
from application.ports.structured_extractor import ExtractedField
from infrastructure.chat.nodes.query_planning import QueryPlanningNode


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

    Retrieval builds its tags from the entity texts plus the author mentions, so
    clearing only the entities left the "unconstrained" arm filtered by author.
    """
    from infrastructure.config import settings

    monkeypatch.setattr(settings, "chat_clear_ner_filters", True)

    node = QueryPlanningNode(
        llm_client=_Fake(),
        prompt_repository=_Fake(),
        ner_extractor=_Fake([NEREntity(text="MRSA", entity_type="gene_name")]),
        structured_extractor=_Fake([ExtractedField(name="author_name", value="Chang", score=0.9)]),
    )
    plan, _ = await node.run(
        "what did Chang report about MRSA?", [], workspace_id=uuid4(), allowed_artifact_ids=None
    )

    assert plan.ner_entity_filters == []
    assert plan.author_mentions == [], "author mentions still become a tag filter"
