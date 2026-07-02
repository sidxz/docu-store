"""ListRecentConversationsUseCase — enriched recent-chat summaries."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from returns.result import Success

from application.dtos.chat_dtos import (
    AgentTraceDTO,
    ChatMessageDTO,
    ConversationDTO,
    QueryContextDTO,
    SourceCitationDTO,
)
from application.use_cases.chat_use_cases import ListRecentConversationsUseCase


def _conv(cid, ws, owner, *, msgs=2, updated=None) -> ConversationDTO:
    now = updated or datetime(2026, 7, 1, tzinfo=UTC)
    return ConversationDTO(
        conversation_id=cid, workspace_id=ws, owner_id=owner,
        title="Latest on FadD32?", created_at=now, updated_at=now,
        message_count=msgs, model_used="claude", is_archived=False,
    )


def _asst(cid, content, *, entities=(), smiles=(), sources=(), grounded=None, conf=None):
    qc = QueryContextDTO(
        ner_entities=[{"entity_text": t, "entity_type": ty} for t, ty in entities],
        smiles_resolved=[{"extracted_ids": list(smiles)}] if smiles else [],
    )
    trace = AgentTraceDTO(grounding_is_grounded=grounded, grounding_confidence=conf)
    return ChatMessageDTO(
        conversation_id=cid, message_id=uuid4(), role="assistant", content=content,
        sources=[SourceCitationDTO(artifact_id=a, artifact_title=t, citation_index=i)
                 for i, (a, t) in enumerate(sources)],
        query_context=qc, agent_trace=trace, created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


class _FakeRepo:
    def __init__(self, convs, messages):
        self._convs = convs
        self._messages = messages  # {conversation_id: [ChatMessageDTO]}
        self.limit_seen = None

    async def list_recent_conversations(self, workspace_id, owner_id, limit):
        self.limit_seen = limit
        return self._convs

    async def get_messages(self, conversation_id, skip=0, limit=100):
        return self._messages.get(conversation_id, [])


@pytest.mark.asyncio
async def test_enriches_entities_snippet_grounding():
    ws, owner, cid = uuid4(), uuid4(), uuid4()
    art = uuid4()
    convs = [_conv(cid, ws, owner)]
    messages = {cid: [
        _asst(cid, "## Heading\nNZ-967 is the **lead** with $IC_{50}$ 0.08 uM.",
              entities=[("FadD32", "target"), ("FadD32", "target"), ("IC50", "assay")],
              smiles=["NZ-967"], sources=[(art, "FadD32 updates")],
              grounded=True, conf=1.0),
    ]}
    repo = _FakeRepo(convs, messages)

    result = await ListRecentConversationsUseCase(repo).execute(ws, owner, limit=5)

    assert isinstance(result, Success)
    [rc] = result.unwrap()
    assert repo.limit_seen == 5
    # snippet is plain-text (no markdown/latex), truncated
    assert "NZ-967 is the lead" in rc.last_answer_snippet
    assert "**" not in rc.last_answer_snippet and "$" not in rc.last_answer_snippet
    # entities deduped (FadD32 once) + compound from smiles, capped at 4
    texts = {e.text for e in rc.entities}
    assert "FadD32" in texts and "IC50" in texts and "NZ-967" in texts
    assert len(rc.entities) <= 4
    assert any(e.type == "compound" and e.text == "NZ-967" for e in rc.entities)
    # cited docs + grounding
    assert rc.cited_documents[0].title == "FadD32 updates"
    assert rc.source_count == 1
    assert rc.grounded is True and rc.grounded_confidence == 1.0


@pytest.mark.asyncio
async def test_entity_cap_and_priority():
    # 6 distinct candidates across types; compound/target/assay must win the top 4.
    ws, owner, cid = uuid4(), uuid4(), uuid4()
    convs = [_conv(cid, ws, owner)]
    messages = {cid: [_asst(
        cid, "answer",
        entities=[
            ("DiseaseX", "disease"),   # low priority
            ("Other", "misc"),         # fallback priority
            ("FadD32", "target"),      # priority 1
            ("IC50", "assay"),         # priority 2
            ("GeneY", "gene"),         # priority 1
        ],
        smiles=["NZ-967"],             # -> compound, priority 0
    )]}

    result = await ListRecentConversationsUseCase(_FakeRepo(convs, messages)).execute(ws, owner)
    [rc] = result.unwrap()

    assert len(rc.entities) == 4  # capped
    kept = {e.text for e in rc.entities}
    # highest-priority types kept; the low-priority disease/misc dropped
    assert "NZ-967" in kept and "FadD32" in kept and "GeneY" in kept and "IC50" in kept
    assert "DiseaseX" not in kept and "Other" not in kept


@pytest.mark.asyncio
async def test_generic_chat_no_entities_no_sources():
    ws, owner, cid = uuid4(), uuid4(), uuid4()
    convs = [_conv(cid, ws, owner)]
    messages = {cid: [_asst(cid, "Yes, they are affiliated with Texas A&M.")]}
    result = await ListRecentConversationsUseCase(_FakeRepo(convs, messages)).execute(ws, owner)
    [rc] = result.unwrap()
    assert rc.entities == []
    assert rc.cited_documents == []
    assert rc.grounded is None  # omitted, no red flag
    assert "Texas A&M" in rc.last_answer_snippet
