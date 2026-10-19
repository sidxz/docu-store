"""A workspace admin's health page shows their workspace, not the platform's layout."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from application.dtos.health_dtos import ConfigSummary
from infrastructure.health.health_checker import InfrastructureHealthChecker


class Vectors:
    def __init__(self, count: int) -> None:
        self.count, self.asked = count, []

    async def count_vectors(self, workspace_id):
        self.asked.append(workspace_id)
        return self.count


class Mongo:
    class admin:  # noqa: N801 - mirrors motor's attribute
        @staticmethod
        async def command(name):
            members = [{"name": "mongo-0.internal:27017", "stateStr": "PRIMARY"}]
            return {} if name == "ping" else {"set": "rs0", "members": members}

    async def server_info(self):
        return {"version": "7.0"}


def _checker(**kw) -> InfrastructureHealthChecker:
    deps = dict(
        mongo_client=None, vector_store=None, compound_vector_store=None,
        summary_vector_store=None, embedding_generator=None, chemberta_generator=None,
        reranker=None, heartbeat_store=None, settings=SimpleNamespace(),
    )
    return InfrastructureHealthChecker(**{**deps, **kw})


async def test_qdrant_counts_only_the_callers_workspace() -> None:
    ws, pages, compounds, summaries = uuid4(), Vectors(3), Vectors(5), Vectors(7)
    checker = _checker(vector_store=pages, compound_vector_store=compounds, summary_vector_store=summaries)
    status = await checker._check_qdrant(ws)
    assert status.details == {
        "collections": {
            "page_embeddings": {"points_count": 3},
            "compound_embeddings": {"points_count": 5},
            "summary_embeddings": {"points_count": 7},
        },
    }
    assert pages.asked == compounds.asked == summaries.asked == [ws]


async def test_no_internal_hosts_or_paths() -> None:
    mongo = await _checker(mongo_client=Mongo())._check_mongodb()
    blob = await _checker(settings=SimpleNamespace(blob_base_url="file:///srv/blobs-missing", blob_storage_options={}))._check_blob_storage()
    assert "mongo-0.internal" not in str(mongo)
    assert "/srv/blobs-missing" not in str(blob)
    assert not {"qdrant_url", "temporal_address", "blob_base_url"} & set(ConfigSummary.model_fields)
