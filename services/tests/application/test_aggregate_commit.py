"""commit(): load fresh → mutate → save, reloading on optimistic-lock conflicts."""

from __future__ import annotations

from uuid import uuid4

import pytest

from application.services.aggregate_commit import commit
from domain.exceptions import ConcurrencyError


class _Agg:
    def __init__(self, version: int) -> None:
        self.version = version
        self.applied: list[str] = []


class _Repo:
    """Every get_by_id hands out a fresh object; save conflicts N times first."""

    def __init__(self, conflicts: int = 0) -> None:
        self.conflicts = conflicts
        self.loads = 0
        self.saved: list[_Agg] = []

    def get_by_id(self, aggregate_id):  # noqa: ANN001
        self.loads += 1
        return _Agg(version=self.loads)

    def save(self, aggregate: _Agg) -> None:
        if self.conflicts:
            self.conflicts -= 1
            raise ConcurrencyError("stream moved")
        self.saved.append(aggregate)


def _mutate(agg: _Agg) -> bool:
    agg.applied.append("x")
    return True


def test_saves_the_freshly_loaded_aggregate() -> None:
    repo = _Repo()
    saved = commit(repo, uuid4(), _mutate)
    assert saved is repo.saved[0] and saved.applied == ["x"] and repo.loads == 1


def test_conflict_reloads_and_retries_without_rerunning_the_caller() -> None:
    repo = _Repo(conflicts=2)
    saved = commit(repo, uuid4(), _mutate)
    assert repo.loads == 3 and saved.version == 3  # third load won
    assert len(repo.saved) == 1


def test_gives_up_after_the_last_attempt() -> None:
    repo = _Repo(conflicts=3)
    with pytest.raises(ConcurrencyError):
        commit(repo, uuid4(), _mutate, attempts=3)
    assert repo.saved == []


def test_no_change_means_no_save() -> None:
    repo = _Repo()
    assert commit(repo, uuid4(), lambda _agg: False) is None
    assert repo.saved == [] and repo.loads == 1
