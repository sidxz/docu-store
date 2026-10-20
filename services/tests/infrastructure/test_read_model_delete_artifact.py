"""delete_artifact drops the artifact and its tag-dictionary entries in one transaction."""

from __future__ import annotations

from types import SimpleNamespace

from infrastructure.read_repositories.mongo_read_model_materializer import (
    MongoReadModelMaterializer,
)


class RecordingCollection:
    def __init__(self, log: list, name: str, *, found: list | None = None) -> None:
        self._log = log
        self._name = name
        self._found = found or []

    def find_one(self, *args, **kwargs):
        return {"workspace_id": "ws-1"}

    def find(self, *args, **kwargs):
        return list(self._found)

    def update_many(self, query, update, session=None):
        self._log.append((self._name, "update_many", query, update))

    def update_one(self, *args, **kwargs):
        self._log.append((self._name, "update_one"))

    def delete_one(self, query, session=None):
        self._log.append((self._name, "delete_one", query))

    def delete_many(self, query, session=None):
        self._log.append((self._name, "delete_many", query))


def test_delete_artifact_clears_its_tags_in_the_same_transaction() -> None:
    log: list = []
    transactions: list = []
    materializer = MongoReadModelMaterializer.__new__(MongoReadModelMaterializer)
    materializer.artifacts = RecordingCollection(log, "artifacts")
    materializer.tag_dictionary = RecordingCollection(log, "tags", found=[{"_id": "t1"}])

    def run_in_transaction(tracking, handler):
        transactions.append(tracking)
        handler(None)

    materializer._run_in_transaction = run_in_transaction

    materializer.delete_artifact("a1", SimpleNamespace(notification_id=7))

    assert len(transactions) == 1
    assert (
        "tags",
        "update_many",
        {"_id": {"$in": ["t1"]}},
        {"$pull": {"artifact_ids": "a1"}},
    ) in log
    # The tag cleanup reads the artifact's workspace, so it must run before the delete.
    pull_at = log.index(
        ("tags", "update_many", {"_id": {"$in": ["t1"]}}, {"$pull": {"artifact_ids": "a1"}})
    )
    assert log.index(("artifacts", "delete_one", {"artifact_id": "a1"})) > pull_at
