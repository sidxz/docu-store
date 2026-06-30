import pytest

from infrastructure.vector_stores.qdrant_store import QdrantStore
from tests.mocks import make_embedding


class _FakeClient:
    def __init__(self): self.upserts = []
    async def upsert(self, collection_name, points): self.upserts.append(points)
    async def delete(self, collection_name, points_selector): pass


@pytest.mark.asyncio
async def test_chunk_metadata_merges_per_chunk(monkeypatch):
    store = QdrantStore(collection_name="test")
    fake = _FakeClient()

    async def _get_client(): return fake
    monkeypatch.setattr(store, "_get_client", _get_client)

    from uuid import uuid4
    page_id, artifact_id = uuid4(), uuid4()
    embs = [make_embedding(), make_embedding()]
    await store.upsert_page_chunk_embeddings(
        page_id=page_id, artifact_id=artifact_id, embeddings=embs,
        page_index=0, chunk_count=2,
        metadata={"workspace_id": "ws"},
        chunk_metadata=[
            {"block_type": "table", "is_table": True, "is_figure": False},
            {"block_type": "paragraph", "is_table": False, "is_figure": False},
        ],
    )
    points = fake.upserts[0]
    assert points[0].payload["block_type"] == "table"
    assert points[0].payload["is_table"] is True
    assert points[0].payload["workspace_id"] == "ws"     # shared metadata still applied
    assert points[1].payload["block_type"] == "paragraph"
    assert points[1].payload["is_table"] is False
