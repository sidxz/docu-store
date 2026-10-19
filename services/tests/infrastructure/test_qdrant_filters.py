from uuid import UUID, uuid4

import pytest
from qdrant_client import models

from infrastructure.vector_stores.qdrant_store import QdrantStore


def _keys(flt: models.Filter) -> list[str]:
    out = []
    for cond in (flt.must or []):
        if isinstance(cond, models.FieldCondition):
            out.append(cond.key)
        elif isinstance(cond, models.Filter) and cond.must:
            out.extend(_keys(cond))
        elif isinstance(cond, models.Filter):
            for sub in (cond.should or []):
                if isinstance(sub, models.FieldCondition):
                    out.append(sub.key)
    return out


def test_build_filter_includes_structure_conditions():
    store = QdrantStore(collection_name="t")
    flt = store._build_filter(
        workspace_id=uuid4(),
        block_types=["table"], section="Methods", is_table=True, is_figure=None,
    )
    keys = _keys(flt)
    assert "workspace_id" in keys  # always tenant-scoped
    assert "block_type" in keys
    assert "section_path_normalized" in keys
    assert "is_table" in keys
    assert "is_figure" not in keys  # None → omitted


def test_build_filter_requires_workspace_id():
    """Fail closed: a tenant-scoped search must never run unfiltered."""
    store = QdrantStore(collection_name="t")
    with pytest.raises(ValueError, match="workspace_id is required"):
        store._build_filter()


class _FakeClient:
    """Just enough Qdrant to watch which payload indexes get ensured."""

    def __init__(self, existing: list[str]) -> None:
        self._existing = existing
        self.indexed: list[str] = []

    async def get_collections(self):
        return models.CollectionsResponse(
            collections=[models.CollectionDescription(name=n) for n in self._existing],
        )

    async def create_payload_index(self, collection_name, field_name, field_schema):
        self.indexed.append(field_name)


async def _ensure(monkeypatch, existing: list[str]) -> _FakeClient:
    store = QdrantStore(collection_name="t")
    client = _FakeClient(existing)
    monkeypatch.setattr(store, "_get_client", lambda: _as_awaitable(client))
    await store.ensure_collection_exists()
    return client


async def _as_awaitable(value):
    return value


async def test_indexes_are_ensured_on_an_existing_collection(monkeypatch):
    """The reason this is not left to collection creation.

    Every deployment already has the collection, so an index added to the list
    would otherwise never be built anywhere it matters -- and a filter on an
    unindexed payload field quietly returns the wrong thing rather than failing.
    """
    client = await _ensure(monkeypatch, existing=["t"])
    assert "source_class" in client.indexed
    assert "workspace_id" in client.indexed


async def test_one_failing_index_does_not_stop_the_rest(monkeypatch):
    """A missing index costs filter performance; refusing to start costs everything."""
    client = await _ensure(monkeypatch, existing=["t"])
    ok = len(client.indexed)

    store = QdrantStore(collection_name="t")
    boom = _FakeClient(["t"])

    async def explode(collection_name, field_name, field_schema):
        boom.indexed.append(field_name)
        if field_name == "workspace_id":
            raise RuntimeError("qdrant said no")

    boom.create_payload_index = explode
    monkeypatch.setattr(store, "_get_client", lambda: _as_awaitable(boom))
    await store.ensure_collection_exists()
    assert len(boom.indexed) == ok  # stepped over, not stopped at


def _tag_subfilter(flt: models.Filter) -> models.Filter:
    """The one nested tag Filter inside a built filter's must-conditions."""
    return next(c for c in flt.must if isinstance(c, models.Filter))


@pytest.mark.parametrize("mode", ["any", "all"])
def test_document_level_tags_never_match_a_table(mode):
    """A table must match on its own tags, never on its document's.

    ``artifact_tag_normalized`` says "this paper mentions Pks13 somewhere", which
    is fine for prose and wrong for a table: the match is the attribution, so a
    compound/IC50 table about a *different* target gets its numbers read as
    Pks13's. Phase D narrows a table's own tags for this reason; document-level
    matching must not route around it.
    """
    store = QdrantStore(collection_name="t")
    sub = _tag_subfilter(
        store._build_filter(workspace_id=uuid4(), tags=["Pks13"], tag_match_mode=mode),
    )

    own, doc = sub.should
    assert own.key == "tag_normalized"          # a table may match this
    assert doc.must[0].key == "artifact_tag_normalized"
    assert doc.must_not[0].key == "is_table"    # ...but not this
    assert doc.must_not[0].match.value is True


def test_page_any_mode_stays_page_only():
    """The strict mode never looked at document tags; it still must not."""
    store = QdrantStore(collection_name="t")
    flt = store._build_filter(
        workspace_id=uuid4(), tags=["Pks13"], tag_match_mode="page_any",
    )
    assert not any(isinstance(c, models.Filter) for c in flt.must)
    assert "tag_normalized" in _keys(flt)


def test_same_model_keeps_the_filter_and_adds_the_model():
    from infrastructure.vector_stores.qdrant_store import same_model

    store = QdrantStore(collection_name="t")
    flt = same_model(store._build_filter(workspace_id=uuid4(), block_types=["table"]), "m")
    assert _keys(flt) == ["workspace_id", "block_type", "model_name"]


def test_same_model_keeps_every_clause_of_the_filter():
    from qdrant_client import QdrantClient

    from infrastructure.vector_stores.qdrant_store import same_model

    client = QdrantClient(":memory:")
    client.create_collection("t", vectors_config=models.VectorParams(size=2, distance="Cosine"))
    client.upsert("t", [
        models.PointStruct(id=i, vector=[1.0, 0.0], payload={"ws": ws, "model_name": m})
        for i, (ws, m) in enumerate([("a", "m"), ("b", "m"), ("a", "old")])
    ])
    not_b = models.Filter(must_not=[models.FieldCondition(key="ws", match=models.MatchValue(value="b"))])
    one_a = models.Filter(must=models.FieldCondition(key="ws", match=models.MatchValue(value="a")))
    for flt in (not_b, one_a):
        hits = client.query_points("t", query=[1.0, 0.0], query_filter=same_model(flt, "m")).points
        assert [h.id for h in hits] == [0]


async def test_workspace_counts_and_stale_vectors_stay_in_the_workspace():
    from qdrant_client import AsyncQdrantClient

    from infrastructure.vector_stores.qdrant_store import count_in_workspace, stale_vectors

    ours, theirs, a, b, c = (str(uuid4()) for _ in range(5))
    client = AsyncQdrantClient(":memory:")
    await client.create_collection("t", vectors_config=models.VectorParams(size=2, distance="Cosine"))
    await client.upsert("t", [
        models.PointStruct(
            id=i, vector=[1.0, 0.0], payload={"workspace_id": ws, "artifact_id": art, "model_name": m}
        )
        for i, (ws, art, m) in enumerate(
            [(ours, a, "new"), (ours, a, "old"), (ours, b, "old"), (theirs, c, "old")]
        )
    ])
    assert await count_in_workspace(client, "t", UUID(ours)) == 3
    assert await stale_vectors(client, "t", UUID(ours), "new") == (3, {a: 1, b: 1})
