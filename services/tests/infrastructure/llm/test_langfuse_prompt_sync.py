"""Publishing the bundled prompts to Langfuse."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import structlog
from langfuse.api import NotFoundError

from infrastructure.llm.prompt_repositories import langfuse_prompt_sync as sync_module
from infrastructure.llm.prompt_repositories.langfuse_prompt_sync import (
    keep_syncing_bundled_prompts,
    start_bundled_prompt_sync,
    sync_bundled_prompts,
)


class FakeLangfuse:
    """Langfuse's prompt store, in memory.

    Versions are numbered from 1; ``latest`` sits on the newest one and a label
    lives on one version at a time, as in Langfuse.
    """

    def __init__(self) -> None:
        self._versions: dict[str, list[dict]] = {}
        self.fail_on: set[str] = set()
        self.down = False
        self.api = SimpleNamespace(prompts=SimpleNamespace(get=self._get))

    def _check(self) -> None:
        if self.down:
            msg = "langfuse down"
            raise ConnectionError(msg)

    def _add(self, name: str, prompt: str, labels: list[str], commit: str | None = None) -> None:
        versions = self._versions.setdefault(name, [])
        for version in versions:
            version["labels"] -= {"latest", *labels}
        versions.append({"prompt": prompt, "labels": {"latest", *labels}, "commit": commit})

    def _get(self, prompt_name: str, *, label: str):
        self._check()
        for number, version in enumerate(self._versions.get(prompt_name, []), start=1):
            if label in version["labels"]:
                return SimpleNamespace(
                    prompt=version["prompt"], version=number, labels=sorted(version["labels"])
                )
        raise NotFoundError(body=None)

    def create_prompt(self, *, name, prompt, labels, type, commit_message=None) -> None:  # noqa: A002
        self._check()
        if name in self.fail_on:
            msg = "langfuse rejected it"
            raise ValueError(msg)
        self._add(name, prompt, labels, commit_message)

    def update_prompt(self, *, name, version, new_labels) -> None:
        self._check()
        for other in self._versions[name]:
            other["labels"] -= set(new_labels)
        self._versions[name][version - 1]["labels"] |= set(new_labels)

    # --- what the tests look at -------------------------------------------------
    def seed(self, name: str, prompt: str, labels: list[str]) -> None:
        """A version this sync did not write: the old seed script, or a person."""
        self._add(name, prompt, labels)

    def labels(self, name: str, version: int) -> set[str]:
        return self._versions[name][version - 1]["labels"]

    def commit(self, name: str, version: int) -> str | None:
        return self._versions[name][version - 1]["commit"]

    def version_count(self, name: str) -> int:
        return len(self._versions.get(name, []))

    def served(self, name: str) -> str:
        """What the app renders: it reads the ``latest`` label."""
        return self._get(name, label="latest").prompt


@pytest.fixture
def fake() -> FakeLangfuse:
    return FakeLangfuse()


def test_fresh_langfuse_gets_every_prompt_once(fake):
    out = sync_bundled_prompts(fake, "2.1.0", {"a": "A", "b": "B"})

    assert out["created"] == ["a", "b"]
    assert fake.labels("a", 1) >= {"bundled", "production", "latest"}
    assert fake.commit("a", 1) == "docu-store 2.1.0"

    again = sync_bundled_prompts(fake, "2.1.0", {"a": "A", "b": "B"})

    assert again == {"created": [], "adopted": [], "unchanged": ["a", "b"]}
    assert fake.version_count("a") == 1


def test_adopts_identical_latest_without_new_version(fake):
    fake.seed("a", "A", labels=["production"])  # what the old seed script left

    out = sync_bundled_prompts(fake, "2.1.0", {"a": "A"})

    assert out["adopted"] == ["a"]
    assert fake.version_count("a") == 1
    assert fake.labels("a", 1) >= {"production", "bundled"}


def test_stale_seed_gets_a_new_version(fake):
    fake.seed("a", "OLD", labels=["production"])

    assert sync_bundled_prompts(fake, "2.1.0", {"a": "A"})["created"] == ["a"]
    assert fake.served("a") == "A"


def test_ui_edit_survives_resync(fake):
    sync_bundled_prompts(fake, "2.1.0", {"a": "A"})
    fake.seed("a", "EDITED", labels=[])  # edited in the Langfuse UI: becomes latest

    out = sync_bundled_prompts(fake, "2.1.0", {"a": "A"})

    assert out["unchanged"] == ["a"]
    assert fake.served("a") == "EDITED"


def test_release_change_supersedes_ui_edit(fake):
    sync_bundled_prompts(fake, "2.1.0", {"a": "A"})
    fake.seed("a", "EDITED", labels=[])

    with structlog.testing.capture_logs() as logs:
        sync_bundled_prompts(fake, "2.2.0", {"a": "A2"})

    assert fake.served("a") == "A2"
    assert fake.version_count("a") == 3
    assert [entry["event"] for entry in logs] == ["langfuse_prompt_sync.superseding_edit"]
    assert logs[0]["edited_version"] == 2


def test_release_change_without_ui_edit_logs_nothing(fake):
    sync_bundled_prompts(fake, "2.1.0", {"a": "A"})

    with structlog.testing.capture_logs() as logs:
        sync_bundled_prompts(fake, "2.2.0", {"a": "A2"})

    assert fake.served("a") == "A2"
    assert logs == []


def test_one_failing_prompt_does_not_block_the_rest(fake):
    fake.fail_on = {"a"}

    with pytest.raises(RuntimeError, match="'a'"):
        sync_bundled_prompts(fake, "2.1.0", {"a": "A", "b": "B"})

    assert fake.served("b") == "B"


def test_unreachable_raises(fake):
    fake.down = True

    with pytest.raises(RuntimeError, match="langfuse down"):
        sync_bundled_prompts(fake, "2.1.0", {"a": "A"})


async def test_retries_until_sync_succeeds(monkeypatch):
    calls = []

    def flaky(client, release, prompts=None):
        calls.append(release)
        if len(calls) < 3:
            msg = "langfuse down"
            raise RuntimeError(msg)
        return {"created": [], "adopted": [], "unchanged": []}

    monkeypatch.setattr(sync_module, "sync_bundled_prompts", flaky)
    monkeypatch.setattr(sync_module, "_client", lambda settings: object())

    await keep_syncing_bundled_prompts(SimpleNamespace(), retry_seconds=0)

    assert len(calls) == 3


def _settings(
    repo_type: str = "langfuse", public_key: str | None = "pk", secret_key: str | None = "sk"
):
    return SimpleNamespace(
        prompt_repository_type=repo_type,
        langfuse_host="http://unused",
        langfuse_public_key=public_key,
        langfuse_secret_key=secret_key,
    )


async def test_sync_is_not_started_without_langfuse():
    assert start_bundled_prompt_sync(_settings(repo_type="yaml")) is None
    assert start_bundled_prompt_sync(_settings(public_key=None, secret_key=None)) is None


async def test_sync_starts_in_the_background_when_langfuse_is_configured(monkeypatch):
    seen = []

    async def record(settings, retry_seconds=60):
        seen.append(settings)

    monkeypatch.setattr(sync_module, "keep_syncing_bundled_prompts", record)
    settings = _settings()

    await start_bundled_prompt_sync(settings)

    assert seen == [settings]
