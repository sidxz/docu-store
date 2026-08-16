# hiledit Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Human-in-the-loop correction of extracted metadata (artifact title/date/tags/authors, page compound mentions) with per-field corrector provenance, a human-corrected mark, and protection from machine overwrites. Spec: `services/design_docs/HILEDIT_CORRECTIONS.md`.

**Architecture:** Reuse the existing per-field value events untouched; add one new `HumanCorrectionRecorded` event per aggregate carrying `corrected_fields` + actor. Machine-called `update_*` command methods silently no-op on human-corrected fields; human corrections go through new `correct_*` commands that trigger the value events directly plus the provenance event (atomic save). Projectors write a `human_corrections` map into the read models; DTOs expose it; FE shows edit dialogs + a corrected-by badge.

**Tech Stack:** Python 3.12 / eventsourcing 9.5.2 / FastAPI / pydantic v2 / Lagom DI / MongoDB read models / pytest. FE: Next.js 16, TanStack Query v5, openapi-fetch, shadcn/ui.

## Global Constraints

- Run all Python via `uv run` from `services/` (e.g. `uv run pytest tests/domain -q`).
- **Never modify existing event class schemas** — eventsourcing 9.5.2 rehydrates via `object.__new__` + stored dict; no upcasters exist in this repo. New event classes only.
- Page events always echo `artifact_id: UUID` and `workspace_id: UUID | None` in their payload (existing convention).
- Field keys in `human_corrections` are the aggregate attribute names: `title_mention`, `tag_mentions`, `author_mentions`, `presentation_date`, `compound_mentions`.
- New RBAC action string: `artifacts:hiledit`.
- No new dependencies (BE or FE).
- Lint: `uv run ruff check .` and `uv run ruff format --check .` must stay clean on touched files (repo uses ruff).
- FE: pnpm from `web/`; typecheck via `pnpm --filter portal exec tsc --noEmit` (verify script name in `apps/portal/package.json` first; use existing `lint`/`typecheck` script if present).
- Commits: conventional style (`feat(domain): …`), end body with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Domain — Artifact `correct_metadata` + machine guards

**Files:**
- Modify: `services/domain/aggregates/artifact.py`
- Test: `services/tests/domain/test_artifact_human_corrections.py` (new; mirror style of existing `services/tests/domain/` artifact tests)

**Interfaces:**
- Produces: `Artifact.HumanCorrectionRecorded` event (`corrected_fields: list[str]`, `corrected_by_id: str`, `corrected_by_name: str | None`, `corrected_at: datetime`); `Artifact.human_corrections: dict[str, dict]` state; `Artifact.correct_metadata(*, corrected_by_id, corrected_by_name, title_mention=UNSET, tag_mentions=UNSET, author_mentions=UNSET, presentation_date=UNSET) -> list[str]`; module-level sentinel `UNSET`.
- Consumes: existing events/VOs only.

- [ ] **Step 1: Write the failing tests**

```python
# services/tests/domain/test_artifact_human_corrections.py
from datetime import UTC, datetime

import pytest

from domain.aggregates.artifact import Artifact
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from domain.value_objects.presentation_date import PresentationDate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.title_mention import TitleMention


def make_artifact() -> Artifact:
    return Artifact.create(
        source_uri=None,
        source_filename="deck.pdf",
        artifact_type=ArtifactType.PRESENTATION,  # use an existing enum member; check artifact_type.py
        mime_type=MimeType.PDF,                   # ditto mime_type.py
        storage_location="blobs/deck.pdf",
    )


def test_correct_metadata_updates_values_and_records_provenance():
    artifact = make_artifact()
    corrected = artifact.correct_metadata(
        corrected_by_id="u-1",
        corrected_by_name="Siddhant Rath",
        title_mention=TitleMention(title="Corrected Title"),
    )
    assert corrected == ["title_mention"]
    assert artifact.title_mention.title == "Corrected Title"
    assert artifact.human_corrections["title_mention"]["corrected_by_id"] == "u-1"
    assert artifact.human_corrections["title_mention"]["corrected_by_name"] == "Siddhant Rath"
    assert isinstance(artifact.human_corrections["title_mention"]["corrected_at"], datetime)
    events = artifact.collect_events()
    assert [type(e).__name__ for e in events[-2:]] == ["TitleMentionUpdated", "HumanCorrectionRecorded"]


def test_correct_metadata_multiple_fields_one_provenance_event():
    artifact = make_artifact()
    corrected = artifact.correct_metadata(
        corrected_by_id="u-1",
        corrected_by_name=None,
        tag_mentions=[TagMention(tag="rho kinase")],
        presentation_date=PresentationDate(date=datetime(2026, 1, 5, tzinfo=UTC), source="human"),
    )
    assert corrected == ["tag_mentions", "presentation_date"]
    names = [type(e).__name__ for e in artifact.collect_events()]
    assert names.count("HumanCorrectionRecorded") == 1


def test_machine_update_skipped_after_human_correction():
    artifact = make_artifact()
    artifact.correct_metadata(
        corrected_by_id="u-1", corrected_by_name=None,
        title_mention=TitleMention(title="Human Title"),
    )
    artifact.update_title_mention(TitleMention(title="Machine Title"))  # must silently no-op
    assert artifact.title_mention.title == "Human Title"


def test_machine_update_untouched_fields_still_work():
    artifact = make_artifact()
    artifact.correct_metadata(
        corrected_by_id="u-1", corrected_by_name=None,
        title_mention=TitleMention(title="Human Title"),
    )
    artifact.update_tag_mentions([TagMention(tag="machine tag")])
    assert artifact.tag_mentions[0].tag == "machine tag"


def test_recorrection_overwrites_provenance():
    artifact = make_artifact()
    artifact.correct_metadata(corrected_by_id="u-1", corrected_by_name="A",
                              title_mention=TitleMention(title="T1"))
    artifact.correct_metadata(corrected_by_id="u-2", corrected_by_name="B",
                              title_mention=TitleMention(title="T2"))
    assert artifact.title_mention.title == "T2"
    assert artifact.human_corrections["title_mention"]["corrected_by_id"] == "u-2"


def test_correct_metadata_noop_when_no_fields_given():
    artifact = make_artifact()
    artifact.collect_events()  # drain
    assert artifact.correct_metadata(corrected_by_id="u-1", corrected_by_name=None) == []
    assert artifact.collect_events() == []


def test_correct_metadata_can_clear_date():
    artifact = make_artifact()
    artifact.update_presentation_date(PresentationDate(date=datetime(2020, 1, 1, tzinfo=UTC)))
    artifact.correct_metadata(corrected_by_id="u-1", corrected_by_name=None, presentation_date=None)
    assert artifact.presentation_date is None
    assert "presentation_date" in artifact.human_corrections


def test_correct_metadata_rejected_on_deleted_artifact():
    artifact = make_artifact()
    artifact.delete()
    with pytest.raises(ValueError, match="deleted"):
        artifact.correct_metadata(corrected_by_id="u-1", corrected_by_name=None,
                                  title_mention=TitleMention(title="X"))


def test_replay_reconstructs_human_corrections():
    artifact = make_artifact()
    artifact.correct_metadata(corrected_by_id="u-1", corrected_by_name="A",
                              title_mention=TitleMention(title="T1"))
    events = artifact.collect_events()
    replayed = None
    for e in events:
        replayed = e.mutate(replayed)
    assert replayed.human_corrections["title_mention"]["corrected_by_id"] == "u-1"
    replayed.update_title_mention(TitleMention(title="Machine"))
    assert replayed.title_mention.title == "T1"
```

Adjust `make_artifact` enum members to real ones from `domain/value_objects/artifact_type.py` / `mime_type.py` before running.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services && uv run pytest tests/domain/test_artifact_human_corrections.py -q`
Expected: FAIL — `AttributeError: ... no attribute 'correct_metadata'`.

- [ ] **Step 3: Implement in `artifact.py`**

Add at module level (after imports):

```python
_UNSET: object = object()
"""Sentinel distinguishing 'field not being corrected' from 'correct to None'."""
```

In `__init__`, after `self.presentation_date = None` line: `self.human_corrections: dict[str, dict] = {}`.

Add guards as the first line after the `is_deleted` check in each of `update_title_mention`, `update_tag_mentions`, `update_author_mentions`, `update_presentation_date` (NOT `update_summary_candidate`, NOT `add_pages`/`remove_pages`), e.g.:

```python
    def update_title_mention(self, title_mention: TitleMention | None) -> None:
        if self.is_deleted:
            msg = "Cannot update title mention on a deleted artifact"
            raise ValueError(msg)
        if "title_mention" in self.human_corrections:
            return  # human correction wins; machine update silently skipped
        self.trigger_event(self.TitleMentionUpdated, title_mention=title_mention)
```

Add the new event + commands + apply at the end of the class (before `Deleted` section is fine):

```python
    # ============================================================================
    # COMMAND METHOD - Human-in-the-loop correction (hiledit)
    # ============================================================================
    class HumanCorrectionRecorded(Aggregate.Event):
        corrected_fields: list[str]
        corrected_by_id: str
        corrected_by_name: str | None
        corrected_at: datetime

    def correct_metadata(
        self,
        *,
        corrected_by_id: str,
        corrected_by_name: str | None,
        title_mention: TitleMention | None | object = _UNSET,
        tag_mentions: list[TagMention] | object = _UNSET,
        author_mentions: list[AuthorMention] | object = _UNSET,
        presentation_date: PresentationDate | None | object = _UNSET,
    ) -> list[str]:
        """Apply human corrections: value events + one provenance event, atomically."""
        if self.is_deleted:
            msg = "Cannot correct metadata on a deleted artifact"
            raise ValueError(msg)
        corrected: list[str] = []
        if title_mention is not _UNSET:
            self.trigger_event(self.TitleMentionUpdated, title_mention=title_mention)
            corrected.append("title_mention")
        if tag_mentions is not _UNSET:
            self.trigger_event(self.TagMentionsUpdated, tag_mentions=tag_mentions)
            corrected.append("tag_mentions")
        if author_mentions is not _UNSET:
            self.trigger_event(self.AuthorMentionsUpdated, author_mentions=author_mentions)
            corrected.append("author_mentions")
        if presentation_date is not _UNSET:
            self.trigger_event(self.PresentationDateUpdated, presentation_date=presentation_date)
            corrected.append("presentation_date")
        if corrected:
            self.trigger_event(
                self.HumanCorrectionRecorded,
                corrected_fields=corrected,
                corrected_by_id=corrected_by_id,
                corrected_by_name=corrected_by_name,
                corrected_at=datetime.now(UTC),
            )
        return corrected

    @event(HumanCorrectionRecorded)
    def _apply_human_correction_recorded(
        self,
        corrected_fields: list[str],
        corrected_by_id: str,
        corrected_by_name: str | None,
        corrected_at: datetime,
    ) -> None:
        for field in corrected_fields:
            self.human_corrections[field] = {
                "corrected_by_id": corrected_by_id,
                "corrected_by_name": corrected_by_name,
                "corrected_at": corrected_at,
            }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services && uv run pytest tests/domain/test_artifact_human_corrections.py tests/domain -q`
Expected: new tests PASS; all existing domain tests still PASS.

- [ ] **Step 5: Commit**

```bash
git add services/domain/aggregates/artifact.py services/tests/domain/test_artifact_human_corrections.py
git commit -m "feat(domain): artifact human corrections with provenance + machine-overwrite guards"
```

---

### Task 2: Domain — Page `correct_compound_mentions` + guard

**Files:**
- Modify: `services/domain/aggregates/page.py`
- Test: `services/tests/domain/test_page_human_corrections.py`

**Interfaces:**
- Produces: `Page.HumanCorrectionRecorded` event (same fields as Artifact's **plus** `artifact_id: UUID`, `workspace_id: UUID | None = None`); `Page.human_corrections: dict[str, dict]`; `Page.correct_compound_mentions(compound_mentions, *, corrected_by_id, corrected_by_name) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# services/tests/domain/test_page_human_corrections.py
from uuid import uuid4

import pytest

from domain.aggregates.page import Page
from domain.value_objects.compound_mention import CompoundMention


def make_page() -> Page:
    return Page.create(name="page-1", artifact_id=uuid4(), index=0, workspace_id=uuid4())


def cm(smiles: str, extracted_id: str | None = None) -> CompoundMention:
    return CompoundMention(smiles=smiles, canonical_smiles=smiles,
                           is_smiles_valid=True, extracted_id=extracted_id)


def test_correct_compound_mentions_records_provenance_and_replaces_list():
    page = make_page()
    page.update_compound_mentions([cm("CCO", "CMX41O")])
    page.correct_compound_mentions(
        [cm("CCO", "CMX410")],
        corrected_by_id="u-1",
        corrected_by_name="Sid",
    )
    assert page.compound_mentions[0].extracted_id == "CMX410"
    prov = page.human_corrections["compound_mentions"]
    assert prov["corrected_by_id"] == "u-1"
    events = page.collect_events()
    last = events[-1]
    assert type(last).__name__ == "HumanCorrectionRecorded"
    assert last.artifact_id == page.artifact_id
    assert last.workspace_id == page.workspace_id


def test_machine_update_skipped_after_correction():
    page = make_page()
    page.correct_compound_mentions([cm("CCO")], corrected_by_id="u-1", corrected_by_name=None)
    page.update_compound_mentions([cm("CCC")])  # CSER/reconcile path — must no-op
    assert page.compound_mentions[0].smiles == "CCO"


def test_correction_rejected_on_deleted_page():
    page = make_page()
    page.delete()
    with pytest.raises(ValueError, match="deleted"):
        page.correct_compound_mentions([cm("CCO")], corrected_by_id="u", corrected_by_name=None)


def test_replay_reconstructs_guard_state():
    page = make_page()
    page.correct_compound_mentions([cm("CCO")], corrected_by_id="u-1", corrected_by_name=None)
    events = page.collect_events()
    replayed = None
    for e in events:
        replayed = e.mutate(replayed)
    replayed.update_compound_mentions([cm("CCC")])
    assert replayed.compound_mentions[0].smiles == "CCO"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd services && uv run pytest tests/domain/test_page_human_corrections.py -q`
Expected: FAIL — no `correct_compound_mentions`.

- [ ] **Step 3: Implement in `page.py`**

`__init__`: add `self.human_corrections: dict[str, dict] = {}` after `self.smiles_embedding_metadata = None`.

Guard in `update_compound_mentions` (after the `is_deleted` check):

```python
        if "compound_mentions" in self.human_corrections:
            return  # human correction wins; machine update silently skipped
```

New event + command + apply (import `datetime`/`UTC` are already imported at top; `CompoundMention` is TYPE_CHECKING-imported — that's fine for annotations since the file uses `from __future__ import annotations`):

```python
    # ============================================================================
    # COMMAND METHOD - Human-in-the-loop correction (hiledit)
    # ============================================================================
    class HumanCorrectionRecorded(Aggregate.Event):
        corrected_fields: list[str]
        corrected_by_id: str
        corrected_by_name: str | None
        corrected_at: datetime
        artifact_id: UUID
        workspace_id: UUID | None = None

    def correct_compound_mentions(
        self,
        compound_mentions: list[CompoundMention],
        *,
        corrected_by_id: str,
        corrected_by_name: str | None,
    ) -> None:
        """Human correction: replace compound mentions + record provenance, atomically."""
        if self.is_deleted:
            msg = "Cannot correct compound mentions on a deleted page"
            raise ValueError(msg)
        self.trigger_event(
            self.CompoundMentionsUpdated,
            compound_mentions=compound_mentions,
            artifact_id=self.artifact_id,
            workspace_id=self.workspace_id,
        )
        self.trigger_event(
            self.HumanCorrectionRecorded,
            corrected_fields=["compound_mentions"],
            corrected_by_id=corrected_by_id,
            corrected_by_name=corrected_by_name,
            corrected_at=datetime.now(UTC),
            artifact_id=self.artifact_id,
            workspace_id=self.workspace_id,
        )

    @event(HumanCorrectionRecorded)
    def _apply_human_correction_recorded(
        self,
        corrected_fields: list[str],
        corrected_by_id: str,
        corrected_by_name: str | None,
        corrected_at: datetime,
        artifact_id: UUID,
        workspace_id: UUID | None = None,
    ) -> None:
        for field in corrected_fields:
            self.human_corrections[field] = {
                "corrected_by_id": corrected_by_id,
                "corrected_by_name": corrected_by_name,
                "corrected_at": corrected_at,
            }
```

NOTE: `page.py` has `if TYPE_CHECKING: from uuid import UUID` — the event class attribute annotations are evaluated by the eventsourcing metaclass, so `UUID` must be importable at runtime for the event definition. Check how existing Page events reference `UUID` in class bodies (they do already — `artifact_id: UUID` on `CompoundMentionsUpdated` works because of `from __future__ import annotations`). Keep the same pattern; if the metaclass needs runtime resolution, move `from uuid import UUID` and `from datetime import datetime` out of TYPE_CHECKING (datetime is already runtime-imported).

- [ ] **Step 4: Run tests**

Run: `cd services && uv run pytest tests/domain/test_page_human_corrections.py tests/domain -q`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add services/domain/aggregates/page.py services/tests/domain/test_page_human_corrections.py
git commit -m "feat(domain): page compound-mention human corrections with provenance + guard"
```

---

### Task 3: Application — AuthContext.name + `CorrectArtifactMetadataUseCase`

**Files:**
- Modify: `services/application/ports/auth.py` (add `name`, `email` properties)
- Create: `services/application/use_cases/correct_metadata_use_cases.py`
- Create: `services/application/dtos/correction_dtos.py`
- Test: `services/tests/application/test_correct_artifact_metadata_use_case.py` (mirror fixture style of existing `tests/application/` artifact use-case tests — they use fake repositories; find e.g. the tests for `UpdateTitleMentionUseCase` and copy the fixture approach)

**Interfaces:**
- Consumes: `Artifact.correct_metadata` (Task 1).
- Produces:
  - `application/dtos/correction_dtos.py`: `CorrectedTagInput(BaseModel)` {`tag: str`, `entity_type: str | None = None`}; `CorrectArtifactMetadataRequest(BaseModel)` {`title: str | None = None`, `presentation_date: datetime.date | None = None`, `tags: list[CorrectedTagInput] | None = None`, `authors: list[str] | None = None`} — **omitted-vs-null via `model_fields_set`**; `HumanCorrectionInfo(BaseModel)` {`corrected_by_id: str`, `corrected_by_name: str | None = None`, `corrected_at: datetime.datetime`}.
  - `CorrectArtifactMetadataUseCase(artifact_repository, external_event_publisher=None).execute(artifact_id: UUID, request: CorrectArtifactMetadataRequest, auth: AuthContext | None) -> Result[ArtifactResponse, AppError]`.
- `AuthContext` protocol gains `name: str` and `email: str` properties (concrete duar `RequestAuth` already provides both).

- [ ] **Step 1: Write the failing tests**

Key cases (write with the repo's existing fake-repo fixtures; assert via aggregate saved into the fake repo):

```python
# services/tests/application/test_correct_artifact_metadata_use_case.py
# (adapt imports/fixtures to the repo's existing fake ArtifactRepository test helper)
import datetime as dt
from uuid import uuid4

import pytest
from returns.result import Failure

from application.dtos.correction_dtos import CorrectArtifactMetadataRequest, CorrectedTagInput
from application.use_cases.correct_metadata_use_cases import CorrectArtifactMetadataUseCase
from domain.value_objects.tag_mention import TagMention, TagSource


@pytest.mark.asyncio
async def test_corrects_title_and_records_actor(fake_artifact_repo, make_saved_artifact, auth_editor):
    artifact = make_saved_artifact()
    uc = CorrectArtifactMetadataUseCase(artifact_repository=fake_artifact_repo)
    result = await uc.execute(
        artifact_id=artifact.id,
        request=CorrectArtifactMetadataRequest(title="Fixed Title"),
        auth=auth_editor,  # fake auth with user_id/name/workspace_id matching artifact
    )
    saved = fake_artifact_repo.get_by_id(artifact.id)
    assert saved.title_mention.title == "Fixed Title"
    assert saved.human_corrections["title_mention"]["corrected_by_id"] == str(auth_editor.user_id)
    assert saved.human_corrections["title_mention"]["corrected_by_name"] == auth_editor.name
    assert result.unwrap().human_corrections  # DTO exposure lands in Task 6; assert present if field exists


@pytest.mark.asyncio
async def test_omitted_fields_untouched_null_clears(fake_artifact_repo, make_saved_artifact, auth_editor):
    artifact = make_saved_artifact(with_date=True, with_title=True)
    uc = CorrectArtifactMetadataUseCase(artifact_repository=fake_artifact_repo)
    await uc.execute(
        artifact_id=artifact.id,
        request=CorrectArtifactMetadataRequest(presentation_date=None),  # explicit null
        auth=auth_editor,
    )
    saved = fake_artifact_repo.get_by_id(artifact.id)
    assert saved.presentation_date is None            # cleared
    assert saved.title_mention is not None            # untouched (omitted)
    assert list(saved.human_corrections) == ["presentation_date"]


@pytest.mark.asyncio
async def test_tag_merge_preserves_existing_rich_mentions(fake_artifact_repo, make_saved_artifact, auth_editor):
    rich = TagMention(tag="Rho Kinase", entity_type="target", tag_normalized="rhokinase",
                      sources=[TagSource(page_id=uuid4(), page_index=0, confidence=0.9)],
                      max_confidence=0.9, page_count=1)
    artifact = make_saved_artifact(tags=[rich])
    uc = CorrectArtifactMetadataUseCase(artifact_repository=fake_artifact_repo)
    await uc.execute(
        artifact_id=artifact.id,
        request=CorrectArtifactMetadataRequest(tags=[
            CorrectedTagInput(tag="rho kinase", entity_type="target"),   # kept → rich preserved
            CorrectedTagInput(tag="autophagy"),                          # new → fresh mention
        ]),
        auth=auth_editor,
    )
    saved = fake_artifact_repo.get_by_id(artifact.id)
    assert saved.tag_mentions[0].sources == rich.sources                 # provenance preserved
    assert saved.tag_mentions[1].tag == "autophagy"
    assert saved.tag_mentions[1].tag_normalized == "autophagy"


@pytest.mark.asyncio
async def test_date_normalized_to_utc_datetime_with_human_source(fake_artifact_repo, make_saved_artifact, auth_editor):
    artifact = make_saved_artifact()
    uc = CorrectArtifactMetadataUseCase(artifact_repository=fake_artifact_repo)
    await uc.execute(
        artifact_id=artifact.id,
        request=CorrectArtifactMetadataRequest(presentation_date=dt.date(2026, 3, 2)),
        auth=auth_editor,
    )
    saved = fake_artifact_repo.get_by_id(artifact.id)
    assert saved.presentation_date.date == dt.datetime(2026, 3, 2, tzinfo=dt.UTC)
    assert saved.presentation_date.source == "human"


@pytest.mark.asyncio
async def test_requires_auth(fake_artifact_repo, make_saved_artifact):
    artifact = make_saved_artifact()
    uc = CorrectArtifactMetadataUseCase(artifact_repository=fake_artifact_repo)
    result = await uc.execute(artifact_id=artifact.id,
                              request=CorrectArtifactMetadataRequest(title="X"), auth=None)
    assert isinstance(result, Failure)


@pytest.mark.asyncio
async def test_empty_request_is_validation_error(fake_artifact_repo, make_saved_artifact, auth_editor):
    artifact = make_saved_artifact()
    uc = CorrectArtifactMetadataUseCase(artifact_repository=fake_artifact_repo)
    result = await uc.execute(artifact_id=artifact.id,
                              request=CorrectArtifactMetadataRequest(), auth=auth_editor)
    assert isinstance(result, Failure)
    assert result.failure().category == "validation"
```

Blank-title rule: `title=""` (or whitespace) → validation Failure; `title=None` clears. Add a test for it.

- [ ] **Step 2: Run to verify failure**

Run: `cd services && uv run pytest tests/application/test_correct_artifact_metadata_use_case.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

`application/ports/auth.py` — add to the protocol:

```python
    @property
    def name(self) -> str: ...
    @property
    def email(self) -> str: ...
```

`application/dtos/correction_dtos.py` — the three models from **Interfaces** above (plain pydantic, `model_config = {"extra": "forbid"}` on the request).

`application/use_cases/correct_metadata_use_cases.py`:

```python
from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from application.mappers.artifact_mappers import ArtifactMapper
from application.use_cases._guards import (
    handle_domain_errors,
    require_artifact_workspace,
    require_editor,
)
from domain.aggregates.artifact import _UNSET
from domain.services.tag_mention_aggregator import _normalize  # reuse; if private-name import is ugly, expose a public `normalize_tag` alias in that module and import it
from domain.value_objects.author_mention import AuthorMention
from domain.value_objects.presentation_date import PresentationDate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.title_mention import TitleMention

if TYPE_CHECKING:
    from uuid import UUID

    from application.dtos.artifact_dtos import ArtifactResponse
    from application.dtos.correction_dtos import CorrectArtifactMetadataRequest, CorrectedTagInput
    from application.ports.auth import AuthContext
    from application.ports.external_event_publisher import ExternalEventPublisher
    from application.ports.repositories.artifact_repository import ArtifactRepository

logger = structlog.get_logger()


def _merge_tags(existing: list[TagMention], submitted: list[CorrectedTagInput]) -> list[TagMention]:
    """Keep the rich existing mention for tags the human retained; fresh mentions for additions."""
    now = dt.datetime.now(dt.UTC)
    by_key = {(m.entity_type, _normalize(m.tag)): m for m in existing}
    merged: list[TagMention] = []
    for s in submitted:
        kept = by_key.get((s.entity_type, _normalize(s.tag)))
        merged.append(
            kept
            if kept is not None
            else TagMention(tag=s.tag, entity_type=s.entity_type,
                            tag_normalized=_normalize(s.tag), date_extracted=now)
        )
    return merged


def _merge_authors(existing: list[AuthorMention], submitted: list[str]) -> list[AuthorMention]:
    now = dt.datetime.now(dt.UTC)
    by_name = {m.name.casefold().strip(): m for m in existing}
    return [
        by_name.get(name.casefold().strip())
        or AuthorMention(name=name.strip(), date_extracted=now)
        for name in submitted
    ]


class CorrectArtifactMetadataUseCase:
    """hiledit: apply human corrections to artifact metadata with provenance."""

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.external_event_publisher = external_event_publisher

    @handle_domain_errors
    async def execute(
        self,
        artifact_id: UUID,
        request: CorrectArtifactMetadataRequest,
        auth: AuthContext | None = None,
    ) -> Result[ArtifactResponse, AppError]:
        require_editor(auth)  # raises → mapped by handle_domain_errors; also guarantees auth is not None

        provided = request.model_fields_set
        if not provided:
            return Failure(AppError("validation", "No fields to correct"))

        artifact = self.artifact_repository.get_by_id(artifact_id)
        require_artifact_workspace(auth, artifact)

        kwargs: dict = {}
        if "title" in provided:
            if request.title is not None and not request.title.strip():
                return Failure(AppError("validation", "Title cannot be blank"))
            kwargs["title_mention"] = (
                TitleMention(title=request.title.strip(), date_extracted=dt.datetime.now(dt.UTC))
                if request.title is not None
                else None
            )
        if "presentation_date" in provided:
            kwargs["presentation_date"] = (
                PresentationDate(
                    date=dt.datetime(request.presentation_date.year,
                                     request.presentation_date.month,
                                     request.presentation_date.day, tzinfo=dt.UTC),
                    source="human",
                    date_extracted=dt.datetime.now(dt.UTC),
                )
                if request.presentation_date is not None
                else None
            )
        if "tags" in provided:
            kwargs["tag_mentions"] = _merge_tags(list(artifact.tag_mentions), request.tags or [])
        if "authors" in provided:
            kwargs["author_mentions"] = _merge_authors(list(artifact.author_mentions), request.authors or [])

        corrected = artifact.correct_metadata(
            corrected_by_id=str(auth.user_id),
            corrected_by_name=auth.name,
            **kwargs,
        )
        self.artifact_repository.save(artifact)
        logger.info("hiledit_artifact_metadata_corrected", artifact_id=str(artifact_id),
                    fields=corrected, corrected_by=str(auth.user_id))

        result = ArtifactMapper.to_artifact_response(artifact)
        if self.external_event_publisher:
            await self.external_event_publisher.notify_artifact_updated(result, sub_type="HumanCorrectionRecorded")
        return Success(result)
```

Check `_guards.require_editor(None)` behavior first — if it raises an exception mapped to `unauthorized`, `auth=None` is already handled; the `test_requires_auth` assertion just needs `Failure`. If `_normalize` in `tag_mention_aggregator` is module-private, add `normalize_tag = _normalize` public alias there and import that instead.

- [ ] **Step 4: Run tests**

Run: `cd services && uv run pytest tests/application/test_correct_artifact_metadata_use_case.py tests/application -q`
Expected: PASS, no regressions. (The `human_corrections` DTO assertion may need to wait for Task 6 — if `ArtifactResponse` lacks the field, drop that single assert line here and re-add it in Task 6.)

- [ ] **Step 5: Commit**

```bash
git add services/application services/tests/application/test_correct_artifact_metadata_use_case.py
git commit -m "feat(app): CorrectArtifactMetadataUseCase with actor provenance and tag/author merge"
```

---

### Task 4: Application — `CorrectPageCompoundMentionsUseCase`

**Files:**
- Modify: `services/application/dtos/correction_dtos.py` (add compound DTOs)
- Modify: `services/application/use_cases/correct_metadata_use_cases.py` (add the use case)
- Test: `services/tests/application/test_correct_page_compounds_use_case.py`

**Interfaces:**
- Consumes: `Page.correct_compound_mentions` (Task 2); the SMILES validator port used by `ExtractCompoundMentionsUseCase` (see `application/use_cases/compound_use_cases.py` — reuse the exact same port/DI key, likely `SmilesValidator`/chemistry port; read the file and mirror its usage + canonicalization calls).
- Produces:
  - `CorrectedCompoundInput(BaseModel)`: {`smiles: str`, `extracted_id: str | None = None`, `internal_id: str | None = None`, `cdd_id: str | None = None`, `chembl_id: str | None = None`, `pdb_id: str | None = None`}.
  - `CorrectPageCompoundMentionsRequest(BaseModel)`: {`compound_mentions: list[CorrectedCompoundInput]`} (empty list allowed → clears all mentions).
  - `CorrectPageCompoundMentionsUseCase(page_repository, smiles_validator, external_event_publisher=None).execute(page_id: UUID, request, auth) -> Result[PageResponse, AppError]`.

- [ ] **Step 1: Write the failing tests**

Cases (same fake-repo style; fake validator that canonicalizes lowercase→uppercase or flags "BAD" as invalid):

```python
@pytest.mark.asyncio
async def test_corrects_label_and_revalidates_smiles(...):
    # page seeded with mention extracted_id="CMX41O"
    # request: [{smiles: "CCO", extracted_id: "CMX410"}]
    # assert saved.compound_mentions[0].extracted_id == "CMX410"
    # assert canonical_smiles set from validator, is_smiles_valid True
    # assert human_corrections["compound_mentions"]["corrected_by_id"] == str(auth.user_id)

@pytest.mark.asyncio
async def test_invalid_smiles_rejected_with_validation_error(...):
    # request contains smiles="BAD" → Failure(AppError("validation", ...)) naming the bad SMILES; nothing saved

@pytest.mark.asyncio
async def test_empty_list_clears_mentions(...):
    # request: [] → saved.compound_mentions == [] and provenance recorded

@pytest.mark.asyncio
async def test_requires_auth(...):
    # auth=None → Failure
```

Write them fully (no placeholders in the actual test file) following Task 3's structure.

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/application/test_correct_page_compounds_use_case.py -q` → FAIL.

- [ ] **Step 3: Implement**

Use case body sketch (adapt validator call names to the real port after reading `compound_use_cases.py`):

```python
class CorrectPageCompoundMentionsUseCase:
    """hiledit: replace a page's compound mentions with human-corrected ones."""

    def __init__(self, page_repository, smiles_validator, external_event_publisher=None) -> None:
        self.page_repository = page_repository
        self.smiles_validator = smiles_validator
        self.external_event_publisher = external_event_publisher

    @handle_domain_errors
    async def execute(self, page_id, request, auth=None):
        require_editor(auth)
        page = self.page_repository.get_by_id(page_id)
        require_page_workspace(auth, page)  # use the existing page guard from _guards (check exact name)

        now = dt.datetime.now(dt.UTC)
        mentions: list[CompoundMention] = []
        for item in request.compound_mentions:
            validation = self.smiles_validator.validate(item.smiles)  # mirror compound_use_cases.py exactly
            if not validation.is_valid:
                return Failure(AppError("validation", f"Invalid SMILES: {item.smiles!r}"))
            mentions.append(CompoundMention(
                smiles=item.smiles,
                canonical_smiles=validation.canonical_smiles,
                is_smiles_valid=True,
                extracted_id=item.extracted_id,
                internal_id=item.internal_id,
                cdd_id=item.cdd_id,
                chembl_id=item.chembl_id,
                pdb_id=item.pdb_id,
                date_extracted=now,
            ))

        page.correct_compound_mentions(mentions,
                                       corrected_by_id=str(auth.user_id),
                                       corrected_by_name=auth.name)
        self.page_repository.save(page)
        result = PageMapper.to_page_response(page)  # check mapper name in application/mappers/
        if self.external_event_publisher:
            await self.external_event_publisher.notify_page_updated(result, sub_type="HumanCorrectionRecorded")  # only if such a method exists; else skip publisher entirely
        return Success(result)
```

Verify: the exact page-workspace guard name in `_guards.py`, the page mapper, whether `ExternalEventPublisher` has a page-update method (if not, omit the publisher from this use case), and the validator's real API (it may return canonical string or an object).

- [ ] **Step 4: Run tests** — `uv run pytest tests/application -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add services/application services/tests/application/test_correct_page_compounds_use_case.py
git commit -m "feat(app): CorrectPageCompoundMentionsUseCase with SMILES revalidation"
```

---

### Task 5: API — routes, `artifacts:hiledit` action, DI wiring, remove dead PATCH routes

**Files:**
- Modify: `services/infrastructure/auth.py` (SERVICE_ACTIONS)
- Modify: `services/interfaces/api/routes/artifact_routes.py`
- Modify: `services/interfaces/api/routes/page_routes.py`
- Modify: `services/infrastructure/di/container.py`
- Modify: `services/application/use_cases/artifact_use_cases.py` (remove dead use cases)
- Test: `services/tests/interfaces/` — mirror existing route-test style (find the tests covering `require_action` on create/upload and copy the fixture pattern)

**Interfaces:**
- Produces: `PATCH /artifacts/{artifact_id}/metadata` (body `CorrectArtifactMetadataRequest` → `ArtifactResponse`); `PUT /pages/{page_id}/compound_mentions` (body `CorrectPageCompoundMentionsRequest` → `PageResponse`). Both: `require_action(auth, "artifacts:hiledit")` + workspace guard + entity `edit` permission, following the exact gate order used by `delete_artifact` (`artifact_routes.py:244-255`).

- [ ] **Step 1: Verify the old per-field artifact PATCH routes are unconsumed**

Run: `rg -n "title_mention\"|tag_mentions\"" /Users/sidx/workspace/docu-store/web/apps /Users/sidx/workspace/docu-store/web/packages/api-client/src/client.ts` and `rg -rn "PATCH.*(title_mention|tag_mentions)" /Users/sidx/workspace/docu-store/web`.
Expected: no FE callers (investigation already found none). If a caller shows up, keep the route and only note it; otherwise proceed with removal.

- [ ] **Step 2: Write failing route tests**

Cases: `PATCH /artifacts/{id}/metadata` → 403 when `check_action` returns False and role isn't admin; 200 + body echo when allowed; `PUT /pages/{id}/compound_mentions` same pair; 400 on empty correction request. Use the existing route-test fixtures (app factory + fake auth override).

- [ ] **Step 3: Run to verify failure** — new tests FAIL (404 route not found).

- [ ] **Step 4: Implement**

1. `infrastructure/auth.py` SERVICE_ACTIONS append:
```python
    {"action": "artifacts:hiledit", "description": "Human-in-the-loop correction of extracted metadata"},
```
2. `artifact_routes.py`: add route (mirror imports/deps of neighbors):
```python
@router.patch("/{artifact_id}/metadata", response_model=ArtifactResponse)
@handle_use_case_errors
async def correct_artifact_metadata(
    artifact_id: UUID,
    request: CorrectArtifactMetadataRequest,
    container: ContainerDep,
    auth: AuthDep,
) -> ArtifactResponse:
    """hiledit: human correction of title/date/tags/authors with provenance."""
    await require_action(auth, "artifacts:hiledit")
    await require_workspace_artifact(container, artifact_id, auth)
    await require_artifact_permission(auth, artifact_id, "edit")
    use_case = container[CorrectArtifactMetadataUseCase]
    return await use_case.execute(artifact_id=artifact_id, request=request, auth=auth)
```
   (Copy the exact dependency aliases/guard helper signatures from the existing `delete_artifact` route — names above are indicative; the file's own idiom wins.)
3. Remove `PATCH /{artifact_id}/title_mention` and `PATCH /{artifact_id}/tag_mentions` routes; keep `summary_candidate`. Remove `UpdateTitleMentionUseCase` + `UpdateTagMentionsUseCase` from `artifact_use_cases.py`, their container registrations, and their tests. (They record no provenance and would silently no-op after a correction — a trap.)
4. `page_routes.py`: add
```python
@router.put("/{page_id}/compound_mentions", response_model=PageResponse)
@handle_use_case_errors
async def correct_page_compound_mentions(...):
    """hiledit: replace compound mentions (labels/SMILES) with human corrections."""
    await require_action(auth, "artifacts:hiledit")
    ...same guard order as its PATCH neighbors + container[CorrectPageCompoundMentionsUseCase]...
```
   Keep the existing `POST /pages/{page_id}/compound_mentions` (append) untouched.
5. `container.py` registrations:
```python
container[CorrectArtifactMetadataUseCase] = lambda c: CorrectArtifactMetadataUseCase(
    artifact_repository=c[ArtifactRepository],
    external_event_publisher=c[ExternalEventPublisher],
)
container[CorrectPageCompoundMentionsUseCase] = lambda c: CorrectPageCompoundMentionsUseCase(
    page_repository=c[PageRepository],
    smiles_validator=c[<same key ExtractCompoundMentionsUseCase uses>],
)
```

- [ ] **Step 5: Run tests** — `uv run pytest tests/interfaces tests/application -q` → PASS (including removal fallout fixed).

- [ ] **Step 6: Commit**

```bash
git add services/infrastructure/auth.py services/interfaces services/infrastructure/di/container.py services/application services/tests
git commit -m "feat(api): hiledit correction endpoints gated on artifacts:hiledit; drop unconsumed per-field PATCH routes"
```

---

### Task 6: Read models — projectors, DTOs, mappers

**Files:**
- Modify: `services/infrastructure/event_projectors/event_projector.py` (routing map)
- Modify: `services/infrastructure/event_projectors/artifact_projector.py`, `page_projector.py`
- Modify: `services/application/dtos/artifact_dtos.py`, `page_dtos.py` (add `human_corrections`)
- Modify: `services/application/mappers/artifact_mappers.py` + the page mapper
- Modify (if needed): `services/infrastructure/read_repositories/mongo_read_repository.py` (only if DTO construction is explicit per-field)
- Test: `services/tests/infrastructure/` projector tests (mirror existing artifact/page projector test style)

**Interfaces:**
- Consumes: `Artifact.HumanCorrectionRecorded` / `Page.HumanCorrectionRecorded` (Tasks 1–2); `HumanCorrectionInfo` DTO (Task 3).
- Produces: read-model subdocument `human_corrections.<field> = {corrected_by_id, corrected_by_name, corrected_at}`; `ArtifactResponse.human_corrections: dict[str, HumanCorrectionInfo]` (default `{}`), same on `PageResponse`.

- [ ] **Step 1: Failing projector tests** — feed a `HumanCorrectionRecorded` event through the projector (existing tests show how events are constructed/dispatched); assert the materializer got `{"human_corrections.title_mention": {...}}` with ISO datetime, and that a second event for another field doesn't wipe the first (dotted-path `$set`).

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement**

Projector handler (artifact; page analogous via `upsert_page`):

```python
def handle_human_correction_recorded(self, event: Artifact.HumanCorrectionRecorded) -> None:
    fields = {
        f"human_corrections.{name}": {
            "corrected_by_id": event.corrected_by_id,
            "corrected_by_name": event.corrected_by_name,
            "corrected_at": event.corrected_at.isoformat(),
        }
        for name in event.corrected_fields
    }
    self._materializer.upsert_document(...)  # use the same artifact upsert call the sibling handlers use, with tracking
```

Register both in the `event_projector.py` routing map next to their siblings.

DTOs: add to `ArtifactResponse` and `PageResponse`:
```python
    human_corrections: dict[str, HumanCorrectionInfo] = Field(
        default_factory=dict,
        description="Per-field human correction provenance (hiledit)",
    )
```
Mappers: `human_corrections={k: HumanCorrectionInfo(**v) for k, v in artifact.human_corrections.items()}` (same for page). Check how `mongo_read_repository.py` builds the DTOs — if it passes whole docs to `model_validate`, nothing more; if explicit fields, add the line.

Re-add the `human_corrections` assert dropped in Task 3 Step 4, if it was dropped.

- [ ] **Step 4: Run** — `uv run pytest tests/infrastructure tests/application tests/interfaces -q` → PASS. Then the full suite: `uv run pytest -q` → PASS (count should be prior-green + new tests).

- [ ] **Step 5: Commit**

```bash
git add services
git commit -m "feat(read-models): project human_corrections provenance into read models and DTOs"
```

---

### Task 7: FE — types, schema regen, mutation hooks

**Files:**
- Modify: `web/packages/types/src/domain/extraction.ts` (add `HumanCorrectionInfo`), `artifact.ts`, `page.ts` (add `human_corrections?: Record<string, HumanCorrectionInfo>`)
- Regenerate: `web/packages/api-client/src/schema.d.ts`
- Modify: `web/apps/portal/src/hooks/use-artifacts.ts`, `use-pages.ts`
- Modify: `web/apps/portal/src/lib/query-keys.ts` only if a needed key is missing

**Interfaces:**
- Produces: `useCorrectArtifactMetadata(artifactId: string)` → mutation accepting `{title?: string | null; presentation_date?: string | null; tags?: {tag: string; entity_type?: string | null}[]; authors?: string[]}`, invalidates `queryKeys.artifacts.detail(artifactId)` + `queryKeys.artifacts.all`; `useCorrectPageCompounds(pageId: string)` → mutation accepting `{compound_mentions: CorrectedCompoundInput[]}`, invalidates `queryKeys.pages.detail(pageId)`.

- [ ] **Step 1: Regenerate the api-client schema**

The generator reads a URL; the BE need not be deployed — dump the schema from the app factory:

```bash
cd services && uv run python -c "
import json
from interfaces.api.main import create_app
print(json.dumps(create_app().openapi()))
" > /private/tmp/claude-501/-Users-sidx-workspace-docu-store/ac4abbc6-9357-4bf8-ad46-443786dbc629/scratchpad/openapi.json
cd ../web && pnpm --filter api-client exec openapi-typescript /private/tmp/claude-501/-Users-sidx-workspace-docu-store/ac4abbc6-9357-4bf8-ad46-443786dbc629/scratchpad/openapi.json -o ./src/schema.d.ts
```

If `create_app()` requires live infra at import time, fall back to starting the dev API per `services/Makefile`. Verify the new paths exist: `rg '"/artifacts/{artifact_id}/metadata"|"/pages/{page_id}/compound_mentions"' web/packages/api-client/src/schema.d.ts` → both present (PATCH + PUT). Diff should also show removal of the dropped PATCH routes.

- [ ] **Step 2: Hand types**

`extraction.ts`:
```ts
/** Mirrors services/application/dtos/correction_dtos.py:HumanCorrectionInfo */
export interface HumanCorrectionInfo {
  corrected_by_id: string;
  corrected_by_name?: string | null;
  corrected_at: string;
}
```
`artifact.ts` + `page.ts`: `human_corrections?: Record<string, HumanCorrectionInfo>;` on the response interfaces.

- [ ] **Step 3: Hooks** (mirror `useShareArtifact` in `use-permissions.ts:25-51` exactly — `apiClient.PATCH/PUT` + `throwApiError` + invalidation):

```ts
export function useCorrectArtifactMetadata(artifactId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: CorrectArtifactMetadataBody) => {
      const { data, error, response } = await apiClient.PATCH(
        "/artifacts/{artifact_id}/metadata",
        { params: { path: { artifact_id: artifactId } }, body },
      );
      if (error) throwApiError("Failed to save corrections", error, response.status);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.artifacts.detail(artifactId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.artifacts.all });
    },
  });
}
```
(`useCorrectPageCompounds` analogous with `apiClient.PUT` and `queryKeys.pages.detail(pageId)`.)

- [ ] **Step 4: Typecheck** — `cd web && pnpm --filter api-client lint && pnpm --filter portal exec tsc --noEmit` (or the portal's own typecheck script) → clean.

- [ ] **Step 5: Commit**

```bash
git add web/packages web/apps/portal/src/hooks
git commit -m "feat(web): hiledit types, regenerated api schema, correction mutation hooks"
```

---

### Task 8: FE — Edit-metadata dialog + corrected-by badge

**Files:**
- Create: `web/apps/portal/src/components/documents/EditMetadataDialog.tsx`
- Create: `web/apps/portal/src/components/documents/HumanCorrectedBadge.tsx`
- Modify: `web/apps/portal/src/app/[workspace]/documents/[id]/page.tsx` (header action + badge next to title)
- Modify: `web/apps/portal/src/components/documents/OverviewTab.tsx` (badges next to Authors/Date/Tags)

**Interfaces:**
- Consumes: `useCorrectArtifactMetadata` (Task 7), `artifact.human_corrections`.
- Produces: `<HumanCorrectedBadge info={HumanCorrectionInfo} />` (icon + tooltip "Corrected by {name ?? id} · {localized date}"); `<EditMetadataDialog artifact={ArtifactResponse} open onOpenChange />`.

- [ ] **Step 1: `HumanCorrectedBadge`** — small: lucide `UserPen` (or `PenLine`) icon inside the existing `Tooltip` primitives, `text-text-muted`, `aria-label="Human corrected"`. Read `components/ui/tooltip.tsx` + `ScoreBadge.tsx` first to match idiom.

- [ ] **Step 2: `EditMetadataDialog`** — model on `ShareDialog.tsx` structure (Dialog + Label/Input rows + footer buttons + sonner toast on success/error):
  - Title: `Input` (empty string ⇒ send `null` to clear).
  - Date: native `<input type="date">` styled with the `Input` component's classes (`className` passthrough); clear button sends `null`.
  - Tags: chips with remove-X + text entry (Enter/comma adds; reuse `TagFilter`'s internals if its props fit, else a ~40-line local chips input in the dialog file — check `TagFilter.tsx` first; it's autocomplete-bound to `/browse/tags/suggest`, which is desirable). Preserve each chip's `entity_type` from `artifact.tag_mentions`; new chips get `entity_type: null`.
  - Authors: same chip pattern, plain strings, no autocomplete.
  - Submit: build the request with **only changed fields** (diff against the artifact prop; omitted ≠ null semantics matter), call `useCorrectArtifactMetadata`, toast, close.
- [ ] **Step 3: Wire in** — pencil `Edit` button in the doc-detail `PageHeader` actions (next to ShareDialog trigger), visible only when `useAuthzHasRole("editor")`. Badges: next to title in header when `human_corrections.title_mention`; in OverviewTab next to the Authors label, Date value, and Tags section header for their keys.
- [ ] **Step 4: Verify** — `pnpm --filter portal exec tsc --noEmit` clean; `pnpm --filter portal lint` clean; `pnpm --filter portal build` succeeds.
- [ ] **Step 5: Commit** — `git add web/apps/portal && git commit -m "feat(web): edit-metadata dialog and human-corrected badges on document detail"`

---

### Task 9: FE — Compound mention editor on page detail

**Files:**
- Create: `web/apps/portal/src/components/documents/EditCompoundDialog.tsx`
- Modify: `web/apps/portal/src/components/documents/CompoundGrid.tsx` (per-card Edit/Delete affordances + Add card, behind an `editable` prop)
- Modify: `web/apps/portal/src/app/[workspace]/documents/[id]/pages/[pageId]/page.tsx` (pass `editable` + `pageId` + `human_corrections` badge on the compounds section)

**Interfaces:**
- Consumes: `useCorrectPageCompounds` (Task 7), `page.compound_mentions`, `HumanCorrectedBadge` (Task 8).
- Produces: full-list PUT on every save (edit one card → send whole corrected array; delete → array minus item; add → array plus item). Round-trip untouched mentions **verbatim** (pass through `internal_id`/`cdd_id`/`chembl_id`/`pdb_id` from the fetched mention; drop derived `canonical_smiles`/`is_smiles_valid` — BE recomputes).

- [ ] **Step 1: `EditCompoundDialog`** — fields: Label (`extracted_id`, Input) + SMILES (Input) + live `<MoleculeStructure smiles={draft} width={220} height={150} />` preview so the user sees the structure before saving. Invalid-SMILES server 400 → sonner error toast (surface detail message).
- [ ] **Step 2: `CompoundGrid` affordances** — when `editable`: pencil + trash icon buttons on each card (trash uses the existing `useConfirm()` provider), plus a dashed "Add compound" card opening the dialog empty. Gate `editable` on `useAuthzHasRole("editor")` at the page level.
- [ ] **Step 3: Badge** — `HumanCorrectedBadge` next to the Compounds section heading when `page.human_corrections?.compound_mentions`.
- [ ] **Step 4: Verify** — tsc + lint + build clean.
- [ ] **Step 5: Commit** — `git add web/apps/portal && git commit -m "feat(web): compound mention editor with structure preview on page detail"`

---

### Task 10: Full verification + review

- [ ] `cd services && uv run pytest -q` — entire suite green.
- [ ] `cd services && uv run ruff check . && uv run ruff format --check .` — clean.
- [ ] `cd web && pnpm --filter portal exec tsc --noEmit && pnpm --filter portal build` — clean.
- [ ] Run `/code-review` on the branch diff; fix confirmed findings.
- [ ] Update `services/design_docs/HILEDIT_CORRECTIONS.md` status line if anything shipped differently.
- [ ] Final commit if fixes were made.

## Self-Review Notes (done at authoring time)

- Spec coverage: §2 matrix → Tasks 1–5; provenance question → Tasks 1–2 (events) + 6 (read models); guards → Tasks 1–2; RBAC → Task 5; FE → Tasks 7–9; rollout seeding is operational (documented in spec §6, no code task).
- Type consistency: field keys (`title_mention`, `tag_mentions`, `author_mentions`, `presentation_date`, `compound_mentions`) and `HumanCorrectionInfo` shape used identically across Tasks 1–8.
- Known intentional look-ups left to implementers (files not fully read at planning time): exact fake-repo fixture names in `tests/application`, materializer artifact-upsert method name, smiles validator port API, page mapper name, portal typecheck script name. Each task says exactly where to look.
