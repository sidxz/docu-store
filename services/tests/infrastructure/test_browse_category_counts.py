"""Browse category counts cover only the artifacts the caller may open.

Talks to a real Mongo (docker-compose locally, CI's mongodb service): the
behaviour under test is the aggregation sent to it.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from infrastructure.read_repositories.mongo_read_repository import MongoReadRepository

pytestmark = pytest.mark.integration

WS, SEEN, HIDDEN = str(uuid4()), uuid4(), uuid4()


def _artifact(artifact_id, compound, author, date):
    return {
        "artifact_id": str(artifact_id),
        "workspace_id": WS,
        "tag_mentions": [
            {"entity_type": "compound_name", "tag": compound},
            {"entity_type": "target", "tag": "InhA"},
        ],
        "author_mentions": [{"name": author}],
        "presentation_date": {"date": date},
    }


@pytest.fixture
async def repo():
    client = AsyncIOMotorClient("mongodb://localhost:27017", serverSelectionTimeoutMS=3000)
    db_name = f"docu_store_test_{uuid4().hex[:8]}"
    try:
        await client.admin.command("ping")
    except Exception as exc:  # pragma: no cover - only hit with no local/CI Mongo
        pytest.skip(f"no Mongo reachable at localhost:27017: {exc}")
    settings = SimpleNamespace(
        mongo_db=db_name,
        mongo_pages_collection="pages",
        mongo_artifacts_collection="artifacts",
        mongo_tag_dictionary_collection="tag_dictionary",
    )
    repo = MongoReadRepository(client, settings)
    await repo.artifacts.insert_many([
        _artifact(SEEN, "BTZ-043", "Rath", "2024-05-01T00:00:00+00:00"),
        _artifact(HIDDEN, "TBA-7371", "Lee", "2023-02-01T00:00:00+00:00"),
    ])
    # The dictionary spans every artifact, visible or not.
    await repo.tag_dictionary.insert_many([
        {"workspace_id": WS, "entity_type": et, "tag": tag, "artifact_ids": ids}
        for et, tag, ids in [
            ("compound_name", "btz-043", [str(SEEN)]),
            ("compound_name", "tba-7371", [str(HIDDEN)]),
            ("target", "inha", [str(SEEN), str(HIDDEN)]),
            ("author", "rath", [str(SEEN)]),
            ("author", "lee", [str(HIDDEN)]),
            ("date", "2024-05-01", [str(SEEN)]),
            ("date", "2023-02-01", [str(HIDDEN)]),
        ]
    ])
    yield repo
    await client.drop_database(db_name)
    client.close()


def _counts(response):
    return {c.entity_type: (c.artifact_count, c.distinct_count) for c in response.categories}


async def test_restricted_caller_counts_only_what_they_can_open(repo):
    response = await repo.get_tag_categories(workspace_id=WS, limit=10, allowed_artifact_ids=[SEEN])
    assert response.total_artifacts == 1
    assert _counts(response) == {
        "compound_name": (1, 1),
        "target": (1, 1),
        "author": (1, 1),
        "date": (1, 1),
    }


async def test_unrestricted_caller_counts_the_whole_workspace(repo):
    response = await repo.get_tag_categories(workspace_id=WS, limit=10)
    assert response.total_artifacts == 2
    assert _counts(response) == {
        "compound_name": (2, 2),
        "target": (2, 1),
        "author": (2, 2),
        "date": (2, 2),
    }
