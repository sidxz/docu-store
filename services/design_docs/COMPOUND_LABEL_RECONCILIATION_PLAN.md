# Compound-Label Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Canonicalize CSER-extracted compound labels (`extracted_id`) against each document's own NER `compound_name` tags at the aggregate source, so every downstream store shows the document's real label (`CMX410`, not the OCR'd `CMX41O`).

**Architecture:** A pure domain glyph-skeleton matcher decides when a CSER label is an OCR variant of a known NER name. A `ReconcileCompoundLabelsUseCase` applies the correction by calling the existing `page.update_compound_mentions(...)` — reusing the `CompoundMentionsUpdated` event so the existing cascade re-derives both the Mongo read model (`PageProjector`) and the Qdrant compound vectors (`EmbedCompoundSmilesWorkflow`). A thin `ReconcileCompoundLabelsWorkflow` is fired from **both** the `TagMentionsUpdated` and `CompoundMentionsUpdated` handlers in `pipeline_worker.py` (rendezvous of the two concurrent ingestion branches). A measure-first backfill script reuses the same use case with `--dry-run` as default.

**Tech Stack:** Python 3.12, event-sourced DDD (`eventsourcing` lib), Temporal (`temporalio`), MongoDB (`motor`), Qdrant, `returns.result`, `pydantic`, `structlog`, `pytest`.

## Global Constraints

- Run every Python command with `uv run` (e.g. `uv run pytest ...`). Never bare `python`/`pytest`.
- Layering: `domain/` imports nothing from `application/` or `infrastructure/`; `application/` may import `domain/`; `infrastructure/` may import both. The matcher is pure domain (no I/O).
- Reuse #1's confusable groups verbatim: `("0Oo", "1IlL", "5S", "8B")`. **Never** bridge two distinct digits — `CMX410` must never resolve to `CMX411`.
- Precision over recall: zero skeleton matches → keep the CSER label. Never invent a label.
- Fix at the source only. Do **not** add a Qdrant `set_payload` path or a direct Mongo write — the corrected `CompoundMentionsUpdated` event re-derives both stores.
- `ConcurrencyError` from a save must propagate (re-raise) so the Temporal activity retries — do not swallow it into a `Failure`.
- Working directory for all paths/commands: `services/`.

---

### Task 1: Domain glyph-skeleton matcher

**Files:**
- Create: `services/domain/services/compound_label_matcher.py`
- Test: `services/tests/domain/test_compound_label_matcher.py`

**Interfaces:**
- Produces: `glyph_skeleton(label: str) -> str` and `reconcile_label(cser_label: str, candidate_names: Iterable[str]) -> str | None`. `reconcile_label` returns the document name to canonicalize to, the CSER label unchanged if it is already a valid document name, or `None` if no candidate is glyph-equal (keep original).

- [ ] **Step 1: Write the failing test**

```python
# services/tests/domain/test_compound_label_matcher.py
"""Pure-function tests for compound-label reconciliation (no I/O).

Mirrors the safety guarantees of the #1 lookup fallback
(tests/infrastructure/test_compound_name_matching.py): bridge glyph-identical
OCR pairs, NEVER distinct digits.
"""

from domain.services.compound_label_matcher import glyph_skeleton, reconcile_label


def test_skeleton_folds_confusable_glyphs_to_digits():
    assert glyph_skeleton("CMX41O") == glyph_skeleton("CMX410")   # letter-O == zero
    assert glyph_skeleton("GSKl23") == glyph_skeleton("GSK123")   # lowercase-L == one
    assert glyph_skeleton("GSK-286") == glyph_skeleton("gsk 286")  # hyphen/space/case


def test_skeleton_keeps_distinct_digits_distinct():
    assert glyph_skeleton("CMX410") != glyph_skeleton("CMX411")


def test_reconcile_bridges_letter_o_for_zero():
    assert reconcile_label("CMX41O", ["CMX410"]) == "CMX410"


def test_reconcile_never_bridges_distinct_digits():
    # The analog-series neighbour must never win.
    assert reconcile_label("CMX41O", ["CMX411"]) is None
    assert reconcile_label("CMX410", ["CMX411"]) is None


def test_reconcile_keeps_original_when_already_a_document_name():
    assert reconcile_label("CMX410", ["CMX410", "GSK286"]) == "CMX410"


def test_reconcile_returns_none_when_no_candidate_matches():
    assert reconcile_label("CMX41O", []) is None
    assert reconcile_label("CMX41O", ["GSK286"]) is None


def test_reconcile_picks_most_frequent_surface_form():
    # NER produced the same compound in two casings; the more frequent one wins.
    assert reconcile_label("CMX41O", ["CMX410", "cmx410", "CMX410"]) == "CMX410"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd services && uv run pytest tests/domain/test_compound_label_matcher.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.services.compound_label_matcher'`

- [ ] **Step 3: Write the minimal implementation**

```python
# services/domain/services/compound_label_matcher.py
"""Domain service: reconcile a CSER-extracted compound label against the
document's own NER compound names, bridging only OCR glyph confusions.

CSER reads labels off page images and confuses visually-identical glyphs
(0/O, 1/I/l, 5/S, 8/B); NER reads the real name from the page text. Two labels
are treated as the same compound iff they share a *glyph skeleton* — each
confusable glyph folded to one canonical digit. The skeleton never merges two
distinct digits, so analog-series neighbours (CMX410 vs CMX411) stay distinct.

Same confusable groups as the #1 lookup fallback
(infrastructure/vector_stores/compound_qdrant_store.py). Kept independent for
now; a later cleanup may point #1 at this domain service.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

# Visually-confusable glyph groups; group[0] is the canonical fold target.
_CONFUSABLE_GROUPS = ("0Oo", "1IlL", "5S", "8B")
_FOLD = {ch: grp[0] for grp in _CONFUSABLE_GROUPS for ch in grp}


def glyph_skeleton(label: str) -> str:
    """Uppercase, strip hyphens/spaces, fold each confusable glyph to its group's
    canonical digit. Two labels are glyph-equal iff their skeletons are equal."""
    normalized = label.strip().upper().replace("-", "").replace(" ", "")
    return "".join(_FOLD.get(ch, ch) for ch in normalized)


def reconcile_label(cser_label: str, candidate_names: Iterable[str]) -> str | None:
    """Return the document name to canonicalize ``cser_label`` to, or None to keep it.

    - Match = same glyph skeleton (never bridges distinct digits).
    - If ``cser_label`` is already among the matches, keep it (return it unchanged).
    - Otherwise return the most frequent matching surface form (deterministic
      tie-break by string) — the document's preferred spelling.
    - No matches → None (keep the original; precision over recall).
    """
    if not cser_label:
        return None
    skeleton = glyph_skeleton(cser_label)
    matches = [n for n in candidate_names if n and glyph_skeleton(n) == skeleton]
    if not matches:
        return None
    if cser_label in matches:
        return cser_label
    counts = Counter(matches)
    return min(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd services && uv run pytest tests/domain/test_compound_label_matcher.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add services/domain/services/compound_label_matcher.py services/tests/domain/test_compound_label_matcher.py
git commit -m "feat(compounds): pure glyph-skeleton matcher for label reconciliation"
```

---

### Task 2: ReconcileCompoundLabelsUseCase + result DTO

**Files:**
- Create: `services/application/dtos/reconcile_dtos.py`
- Create: `services/application/use_cases/reconcile_compound_labels_use_case.py`
- Test: `services/tests/application/test_reconcile_compound_labels_use_case.py`

**Interfaces:**
- Consumes: `reconcile_label` (Task 1); `page.compound_mentions`, `page.tag_mentions`, `page.artifact_id`, `page.update_compound_mentions(list)` (existing `domain/aggregates/page.py:113`); `PageRepository.get_by_id(UUID) -> Page` (sync), `PageRepository.save(Page)` (sync).
- Produces: `ReconcileCompoundLabelsUseCase.execute(page_id: UUID, candidate_names: list[str] | None = None, dry_run: bool = False) -> Result[ReconcileResultDTO, AppError]`. `candidate_names=None` → same-page scope (live path); a list → that scope (backfill). `dry_run=True` computes changes without saving/emitting. `ReconcileResultDTO(page_id, artifact_id, changes: list[LabelChange], applied: bool)`, `LabelChange(before: str, after: str)`.

- [ ] **Step 1: Write the failing test**

```python
# services/tests/application/test_reconcile_compound_labels_use_case.py
import asyncio
from uuid import uuid4

from returns.result import Success

from application.use_cases.reconcile_compound_labels_use_case import (
    ReconcileCompoundLabelsUseCase,
)
from domain.value_objects.compound_mention import CompoundMention
from domain.value_objects.tag_mention import TagMention


class FakePage:
    def __init__(self, page_id, artifact_id, compound_mentions, tag_mentions):
        self.id = page_id
        self.artifact_id = artifact_id
        self.workspace_id = None
        self.compound_mentions = compound_mentions
        self.tag_mentions = tag_mentions
        self.updated_with = None

    def update_compound_mentions(self, mentions):
        self.updated_with = mentions
        self.compound_mentions = mentions


class FakeRepo:
    def __init__(self, page):
        self.page = page
        self.saved = False

    def get_by_id(self, _page_id):
        return self.page

    def save(self, _page):
        self.saved = True


def _page_with(cser_label, ner_name):
    return FakePage(
        page_id=uuid4(),
        artifact_id=uuid4(),
        compound_mentions=[
            CompoundMention(
                smiles="C", canonical_smiles="C", is_smiles_valid=True, extracted_id=cser_label,
            ),
        ],
        tag_mentions=(
            [TagMention(tag=ner_name, entity_type="compound_name")] if ner_name else []
        ),
    )


def test_reconciles_and_emits_when_label_changes():
    page = _page_with("CMX41O", "CMX410")
    repo = FakeRepo(page)
    uc = ReconcileCompoundLabelsUseCase(page_repository=repo)

    result = asyncio.run(uc.execute(page.id))

    assert isinstance(result, Success)
    dto = result.unwrap()
    assert dto.applied is True
    assert [(c.before, c.after) for c in dto.changes] == [("CMX41O", "CMX410")]
    assert page.updated_with is not None
    assert page.updated_with[0].extracted_id == "CMX410"
    assert page.updated_with[0].smiles == "C"  # other fields preserved
    assert repo.saved is True


def test_no_change_does_not_emit_or_save():
    page = _page_with("CMX410", "CMX410")
    repo = FakeRepo(page)
    uc = ReconcileCompoundLabelsUseCase(page_repository=repo)

    dto = asyncio.run(uc.execute(page.id)).unwrap()

    assert dto.applied is False
    assert dto.changes == []
    assert page.updated_with is None
    assert repo.saved is False


def test_no_compound_name_tags_is_noop():
    page = _page_with("CMX41O", None)
    repo = FakeRepo(page)
    uc = ReconcileCompoundLabelsUseCase(page_repository=repo)

    dto = asyncio.run(uc.execute(page.id)).unwrap()

    assert dto.applied is False
    assert repo.saved is False


def test_dry_run_reports_changes_without_saving():
    page = _page_with("CMX41O", "CMX410")
    repo = FakeRepo(page)
    uc = ReconcileCompoundLabelsUseCase(page_repository=repo)

    dto = asyncio.run(uc.execute(page.id, candidate_names=["CMX410"], dry_run=True)).unwrap()

    assert dto.applied is False
    assert [(c.before, c.after) for c in dto.changes] == [("CMX41O", "CMX410")]
    assert page.updated_with is None
    assert repo.saved is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd services && uv run pytest tests/application/test_reconcile_compound_labels_use_case.py -v`
Expected: FAIL with `ModuleNotFoundError` for `reconcile_compound_labels_use_case`.

- [ ] **Step 3: Write the DTO**

```python
# services/application/dtos/reconcile_dtos.py
from uuid import UUID

from pydantic import BaseModel


class LabelChange(BaseModel):
    """One reconciled compound label."""

    before: str
    after: str


class ReconcileResultDTO(BaseModel):
    """Result returned by ReconcileCompoundLabelsUseCase."""

    page_id: UUID
    artifact_id: UUID
    changes: list[LabelChange]
    applied: bool
```

- [ ] **Step 4: Write the use case**

```python
# services/application/use_cases/reconcile_compound_labels_use_case.py
from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from application.dtos.reconcile_dtos import LabelChange, ReconcileResultDTO
from domain.exceptions import AggregateNotFoundError, ConcurrencyError
from domain.services.compound_label_matcher import reconcile_label

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.repositories.page_repository import PageRepository

logger = structlog.get_logger()


class ReconcileCompoundLabelsUseCase:
    """Canonicalize CSER compound labels against the document's NER compound names.

    Reuses ``page.update_compound_mentions`` so the emitted ``CompoundMentionsUpdated``
    event re-derives both the Mongo read model and the Qdrant compound vectors.
    Idempotent: emits only when a label actually changes.
    """

    def __init__(self, page_repository: PageRepository) -> None:
        self.page_repository = page_repository

    async def execute(
        self,
        page_id: UUID,
        candidate_names: list[str] | None = None,
        dry_run: bool = False,
    ) -> Result[ReconcileResultDTO, AppError]:
        try:
            page = self.page_repository.get_by_id(page_id)

            if candidate_names is None:
                names = [
                    tm.tag
                    for tm in (page.tag_mentions or [])
                    if tm.entity_type == "compound_name" and tm.tag
                ]
            else:
                names = candidate_names

            mentions = page.compound_mentions or []
            if not mentions or not names:
                return Success(
                    ReconcileResultDTO(
                        page_id=page_id,
                        artifact_id=page.artifact_id,
                        changes=[],
                        applied=False,
                    ),
                )

            changes: list[LabelChange] = []
            new_mentions = []
            for m in mentions:
                target = reconcile_label(m.extracted_id or "", names)
                if target and target != m.extracted_id:
                    changes.append(LabelChange(before=m.extracted_id, after=target))
                    new_mentions.append(m.model_copy(update={"extracted_id": target}))
                else:
                    new_mentions.append(m)

            if not changes or dry_run:
                return Success(
                    ReconcileResultDTO(
                        page_id=page_id,
                        artifact_id=page.artifact_id,
                        changes=changes,
                        applied=False,
                    ),
                )

            page.update_compound_mentions(new_mentions)
            self.page_repository.save(page)
            logger.info(
                "compound_labels_reconciled",
                page_id=str(page_id),
                artifact_id=str(page.artifact_id),
                changes=[(c.before, c.after) for c in changes],
            )
            return Success(
                ReconcileResultDTO(
                    page_id=page_id,
                    artifact_id=page.artifact_id,
                    changes=changes,
                    applied=True,
                ),
            )

        except ConcurrencyError:
            # Let Temporal retry — do NOT swallow into a Failure.
            raise
        except AggregateNotFoundError as e:
            logger.warning("reconcile_compound_labels_not_found", page_id=str(page_id), error=str(e))
            return Failure(AppError("not_found", str(e)))
        except Exception as e:
            logger.exception(
                "reconcile_compound_labels_unexpected_error",
                page_id=str(page_id),
                error=str(e),
            )
            return Failure(AppError("internal_error", f"Unexpected error: {e!s}"))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd services && uv run pytest tests/application/test_reconcile_compound_labels_use_case.py -v`
Expected: PASS (4 passed)

> If `application/dtos/errors.py` exposes `AppError` with different arg names, match the exact constructor used in `application/use_cases/smiles_embedding_use_cases.py` (`AppError("not_found", str(e))`). Do not change `AppError`.

- [ ] **Step 6: Commit**

```bash
git add services/application/dtos/reconcile_dtos.py services/application/use_cases/reconcile_compound_labels_use_case.py services/tests/application/test_reconcile_compound_labels_use_case.py
git commit -m "feat(compounds): ReconcileCompoundLabelsUseCase (source-side relabel via existing cascade)"
```

---

### Task 3: Trigger use case + orchestrator start method

**Files:**
- Create: `services/application/workflow_use_cases/trigger_compound_label_reconciliation_use_case.py`
- Modify: `services/application/ports/workflow_orchestrator.py` (add abstract method after `start_smiles_embedding_workflow`, ~line 71)
- Modify: `services/infrastructure/temporal/orchestrator.py` (add concrete method after `start_smiles_embedding_workflow`, ~line 135)
- Test: `services/tests/application/test_trigger_compound_label_reconciliation.py`

**Interfaces:**
- Consumes: `WorkflowOrchestrator.start_reconcile_compound_labels_workflow(page_id: UUID) -> None`.
- Produces: `TriggerCompoundLabelReconciliationUseCase(workflow_orchestrator).execute(page_id: UUID) -> WorkflowStartedResponse` with `workflow_id == f"reconcile-compound-labels-{page_id}"`.

- [ ] **Step 1: Write the failing test**

```python
# services/tests/application/test_trigger_compound_label_reconciliation.py
import asyncio
from uuid import uuid4

from application.workflow_use_cases.trigger_compound_label_reconciliation_use_case import (
    TriggerCompoundLabelReconciliationUseCase,
)


class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    async def start_reconcile_compound_labels_workflow(self, page_id):
        self.calls.append(page_id)


def test_trigger_starts_workflow_and_returns_id():
    orch = FakeOrchestrator()
    uc = TriggerCompoundLabelReconciliationUseCase(workflow_orchestrator=orch)
    page_id = uuid4()

    resp = asyncio.run(uc.execute(page_id))

    assert orch.calls == [page_id]
    assert resp.workflow_id == f"reconcile-compound-labels-{page_id}"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd services && uv run pytest tests/application/test_trigger_compound_label_reconciliation.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Add the port method**

In `services/application/ports/workflow_orchestrator.py`, immediately after the `start_smiles_embedding_workflow` block (after line 71, before `start_page_summarization_workflow`):

```python
    @abstractmethod
    async def start_reconcile_compound_labels_workflow(
        self,
        page_id: UUID,
    ) -> None:
        """Start the compound-label reconciliation workflow for a page.

        Reconciles CSER extracted_ids against the page's NER compound_name tags.
        Uses ALLOW_DUPLICATE so it re-runs when triggered by either ingestion branch.

        Args:
            page_id: Unique identifier of the page to reconcile.

        """
        ...
```

- [ ] **Step 4: Add the concrete orchestrator method**

In `services/infrastructure/temporal/orchestrator.py`, after `start_smiles_embedding_workflow` (after line 135). `WorkflowIDReusePolicy` is already imported (used at line 181):

```python
    async def start_reconcile_compound_labels_workflow(
        self,
        page_id: UUID,
    ) -> None:
        """Start the compound-label reconciliation workflow for a page."""
        await self._ensure_client()

        workflow_id = f"reconcile-compound-labels-{page_id}"

        try:
            await self._client.start_workflow(
                "ReconcileCompoundLabelsWorkflow",
                str(page_id),
                id=workflow_id,
                task_queue="artifact_processing",
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
            )
            logger.info("reconcile_compound_labels_workflow_started", page_id=str(page_id))
        except Exception as e:
            logger.exception(
                "failed_to_start_reconcile_compound_labels_workflow",
                page_id=str(page_id),
                error=str(e),
            )
```

- [ ] **Step 5: Write the trigger use case**

```python
# services/application/workflow_use_cases/trigger_compound_label_reconciliation_use_case.py
from uuid import UUID

from application.dtos.workflow_dtos import WorkflowStartedResponse
from application.ports.workflow_orchestrator import WorkflowOrchestrator


class TriggerCompoundLabelReconciliationUseCase:
    """Trigger the compound-label reconciliation workflow for a page.

    Starts the Temporal workflow and returns a WorkflowStartedResponse.
    Temporal is the source of truth for workflow status.
    """

    def __init__(self, workflow_orchestrator: WorkflowOrchestrator) -> None:
        self.workflow_orchestrator = workflow_orchestrator

    async def execute(self, page_id: UUID) -> WorkflowStartedResponse:
        workflow_id = f"reconcile-compound-labels-{page_id}"
        await self.workflow_orchestrator.start_reconcile_compound_labels_workflow(page_id=page_id)
        return WorkflowStartedResponse(workflow_id=workflow_id)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd services && uv run pytest tests/application/test_trigger_compound_label_reconciliation.py -v`
Expected: PASS (1 passed)

- [ ] **Step 7: Commit**

```bash
git add services/application/workflow_use_cases/trigger_compound_label_reconciliation_use_case.py services/application/ports/workflow_orchestrator.py services/infrastructure/temporal/orchestrator.py services/tests/application/test_trigger_compound_label_reconciliation.py
git commit -m "feat(compounds): reconcile trigger use case + orchestrator start method"
```

---

### Task 4: Temporal workflow + activity + worker registration

**Files:**
- Create: `services/infrastructure/temporal/workflows/reconcile_compound_labels_workflow.py`
- Create: `services/infrastructure/temporal/activities/reconcile_compound_labels_activities.py`
- Modify: `services/infrastructure/temporal/worker.py` (imports + resolve + create activity + register in both lists)
- Test: `services/tests/infrastructure/test_reconcile_compound_labels_activity.py`

**Interfaces:**
- Consumes: `ReconcileCompoundLabelsUseCase.execute` (Task 2); `ReconcileResultDTO` with `.changes` and `.applied`.
- Produces: `ReconcileCompoundLabelsWorkflow` (Temporal `name="ReconcileCompoundLabelsWorkflow"`); `create_reconcile_compound_labels_activity(use_case) -> Callable[[str], dict]` (activity `name="reconcile_compound_labels"`).

- [ ] **Step 1: Write the failing test**

```python
# services/tests/infrastructure/test_reconcile_compound_labels_activity.py
import asyncio
from uuid import uuid4

from returns.result import Success

from application.dtos.reconcile_dtos import LabelChange, ReconcileResultDTO
from infrastructure.temporal.activities.reconcile_compound_labels_activities import (
    create_reconcile_compound_labels_activity,
)


class FakeUseCase:
    def __init__(self, dto):
        self._dto = dto
        self.called_with = None

    async def execute(self, page_id):
        self.called_with = page_id
        return Success(self._dto)


def test_activity_maps_success_dto_to_dict():
    page_id = uuid4()
    dto = ReconcileResultDTO(
        page_id=page_id,
        artifact_id=uuid4(),
        changes=[LabelChange(before="CMX41O", after="CMX410")],
        applied=True,
    )
    activity_fn = create_reconcile_compound_labels_activity(use_case=FakeUseCase(dto))

    out = asyncio.run(activity_fn(str(page_id)))

    assert out == {"status": "success", "page_id": str(page_id), "changed": 1, "applied": True}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd services && uv run pytest tests/infrastructure/test_reconcile_compound_labels_activity.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the workflow**

```python
# services/infrastructure/temporal/workflows/reconcile_compound_labels_workflow.py
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="ReconcileCompoundLabelsWorkflow")
class ReconcileCompoundLabelsWorkflow:
    """Reconcile CSER compound labels against NER compound_name tags for a page.

    Idempotent: the use case emits a corrected CompoundMentionsUpdated only when a
    label actually changes, so re-runs after the label is canonical are no-ops.
    """

    @workflow.run
    async def run(self, page_id: str) -> dict:
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            maximum_interval=timedelta(seconds=60),
            maximum_attempts=3,
            backoff_coefficient=2.0,
        )

        result = await workflow.execute_activity(
            "reconcile_compound_labels",
            page_id,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )

        workflow.logger.info(
            f"Compound-label reconciliation completed for page_id={page_id}, result={result}",
        )

        return result
```

- [ ] **Step 4: Write the activity**

```python
# services/infrastructure/temporal/activities/reconcile_compound_labels_activities.py
from collections.abc import Callable
from uuid import UUID

import structlog
from returns.result import Success
from temporalio import activity

from application.use_cases.reconcile_compound_labels_use_case import (
    ReconcileCompoundLabelsUseCase,
)

logger = structlog.get_logger()


def create_reconcile_compound_labels_activity(
    use_case: ReconcileCompoundLabelsUseCase,
) -> Callable[[str], dict]:
    """Create the reconcile_compound_labels activity with injected dependencies."""

    @activity.defn(name="reconcile_compound_labels")
    async def reconcile_compound_labels_activity(page_id: str) -> dict:
        logger.info("reconcile_compound_labels_activity_start", page_id=page_id)

        try:
            page_uuid = UUID(page_id)
            result = await use_case.execute(page_id=page_uuid)
        except Exception as e:
            logger.exception(
                "reconcile_compound_labels_activity_exception",
                page_id=page_id,
                error=str(e),
            )
            raise
        else:
            if isinstance(result, Success):
                dto = result.unwrap()
                logger.info(
                    "reconcile_compound_labels_activity_success",
                    page_id=page_id,
                    changed=len(dto.changes),
                    applied=dto.applied,
                )
                return {
                    "status": "success",
                    "page_id": page_id,
                    "changed": len(dto.changes),
                    "applied": dto.applied,
                }

            error = result.failure()
            logger.error(
                "reconcile_compound_labels_activity_failed",
                page_id=page_id,
                error_code=error.category,
                error_message=error.message,
            )
            return {
                "status": "failed",
                "page_id": page_id,
                "error_code": error.category,
                "error_message": error.message,
            }

    return reconcile_compound_labels_activity
```

- [ ] **Step 5: Register in the worker**

In `services/infrastructure/temporal/worker.py`:

Add to the use-case imports (near line 27):
```python
from application.use_cases.reconcile_compound_labels_use_case import (
    ReconcileCompoundLabelsUseCase,
)
```
Add to the activity-factory imports (near line 55):
```python
from infrastructure.temporal.activities.reconcile_compound_labels_activities import (
    create_reconcile_compound_labels_activity,
)
```
Add to the workflow imports (near line 77):
```python
from infrastructure.temporal.workflows.reconcile_compound_labels_workflow import (
    ReconcileCompoundLabelsWorkflow,
)
```
Resolve the use case (after line 123, `parse_artifact_use_case = ...`):
```python
    reconcile_compound_labels_use_case = container[ReconcileCompoundLabelsUseCase]
```
Create the activity (after line 153, `parse_artifact_activity = ...`):
```python
    reconcile_compound_labels_activity = create_reconcile_compound_labels_activity(
        use_case=reconcile_compound_labels_use_case,
    )
```
Add `ReconcileCompoundLabelsWorkflow,` to the `workflows=[...]` list (after line 170) and `reconcile_compound_labels_activity,` to the `activities=[...]` list (after line 183).

- [ ] **Step 6: Run the test + import-smoke the worker**

Run: `cd services && uv run pytest tests/infrastructure/test_reconcile_compound_labels_activity.py -v`
Expected: PASS (1 passed)

Run: `cd services && uv run python -c "import infrastructure.temporal.worker"`
Expected: no output, exit 0 (module imports — all workflow/activity symbols resolve).

- [ ] **Step 7: Commit**

```bash
git add services/infrastructure/temporal/workflows/reconcile_compound_labels_workflow.py services/infrastructure/temporal/activities/reconcile_compound_labels_activities.py services/infrastructure/temporal/worker.py services/tests/infrastructure/test_reconcile_compound_labels_activity.py
git commit -m "feat(compounds): ReconcileCompoundLabelsWorkflow + activity + worker registration"
```

---

### Task 5: DI wiring + pipeline_worker rendezvous triggers

**Files:**
- Modify: `services/infrastructure/di/container.py` (imports + two registrations after line 617)
- Modify: `services/infrastructure/pipeline_worker.py` (import + resolve after line 89 + trigger call in both handlers)
- Test: `services/tests/infrastructure/test_reconcile_container_wiring.py`

**Interfaces:**
- Consumes: `ReconcileCompoundLabelsUseCase` (Task 2), `TriggerCompoundLabelReconciliationUseCase` (Task 3), `PageRepository`, `WorkflowOrchestrator` (existing container keys).
- Produces: `create_container()[ReconcileCompoundLabelsUseCase]` and `[TriggerCompoundLabelReconciliationUseCase]` resolve; `pipeline_worker` fires reconciliation on both `CompoundMentionsUpdated` and `TagMentionsUpdated`.

- [ ] **Step 1: Write the failing test**

```python
# services/tests/infrastructure/test_reconcile_container_wiring.py
from application.use_cases.reconcile_compound_labels_use_case import (
    ReconcileCompoundLabelsUseCase,
)
from application.workflow_use_cases.trigger_compound_label_reconciliation_use_case import (
    TriggerCompoundLabelReconciliationUseCase,
)
from infrastructure.di.container import create_container


def test_container_resolves_reconcile_use_cases():
    container = create_container()
    assert isinstance(container[ReconcileCompoundLabelsUseCase], ReconcileCompoundLabelsUseCase)
    assert isinstance(
        container[TriggerCompoundLabelReconciliationUseCase],
        TriggerCompoundLabelReconciliationUseCase,
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd services && uv run pytest tests/infrastructure/test_reconcile_container_wiring.py -v`
Expected: FAIL — `container[...]` raises `KeyError`/resolution error for the unregistered use cases.

- [ ] **Step 3: Register in the container**

In `services/infrastructure/di/container.py`, add to the use-case imports (near line 86 and near line 132 where `TriggerSmilesEmbeddingUseCase` is imported):
```python
from application.use_cases.reconcile_compound_labels_use_case import (
    ReconcileCompoundLabelsUseCase,
)
from application.workflow_use_cases.trigger_compound_label_reconciliation_use_case import (
    TriggerCompoundLabelReconciliationUseCase,
)
```
Register both, immediately after the `TriggerSmilesEmbeddingUseCase` block (after line 617):
```python
    container[ReconcileCompoundLabelsUseCase] = lambda c: ReconcileCompoundLabelsUseCase(
        page_repository=c[PageRepository],
    )
    container[TriggerCompoundLabelReconciliationUseCase] = (
        lambda c: TriggerCompoundLabelReconciliationUseCase(
            workflow_orchestrator=c[WorkflowOrchestrator],
        )
    )
```

- [ ] **Step 4: Run the wiring test to verify it passes**

Run: `cd services && uv run pytest tests/infrastructure/test_reconcile_container_wiring.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Wire the rendezvous triggers in pipeline_worker**

In `services/infrastructure/pipeline_worker.py`:

Add the import (near line 54):
```python
from application.workflow_use_cases.trigger_compound_label_reconciliation_use_case import (
    TriggerCompoundLabelReconciliationUseCase,
)
```
Resolve it (after line 89, `trigger_smiles_embedding_use_case = ...`):
```python
    trigger_compound_label_reconciliation_use_case = container[
        TriggerCompoundLabelReconciliationUseCase
    ]
```
In the `Page.CompoundMentionsUpdated` handler, after the smiles trigger (after line 304, following the `pipeline_smiles_embedding_workflow_triggered` log):
```python
                                # Reverse-race + bulk-reprocess self-heal: reconcile
                                # once NER tags are (or later become) present.
                                await trigger_compound_label_reconciliation_use_case.execute(
                                    page_id=domain_event.originator_id,
                                )
```
In the `Page.TagMentionsUpdated` handler, after the `sync_page_tags_use_case.execute(...)` call (after line 321):
```python
                                # Common case: NER finished last — reconcile CSER
                                # labels against the compound_name tags just landed.
                                await trigger_compound_label_reconciliation_use_case.execute(
                                    page_id=domain_event.originator_id,
                                )
```

- [ ] **Step 6: Import-smoke the pipeline worker**

Run: `cd services && uv run python -c "import infrastructure.pipeline_worker"`
Expected: no output, exit 0.

- [ ] **Step 7: Commit**

```bash
git add services/infrastructure/di/container.py services/infrastructure/pipeline_worker.py services/tests/infrastructure/test_reconcile_container_wiring.py
git commit -m "feat(compounds): wire reconcile DI + rendezvous triggers on both ingestion events"
```

---

### Task 6: Measure-first backfill script

**Files:**
- Create: `services/scripts/reconcile_compound_labels.py`
- Test: `services/tests/scripts/test_reconcile_backfill_report.py`

**Interfaces:**
- Consumes: `ReconcileCompoundLabelsUseCase.execute(page_id, candidate_names=..., dry_run=...)` (Task 2); Mongo `page_read_models` (`settings.mongo_pages_collection`) and `artifact_read_models` (`settings.mongo_artifacts_collection`).
- Produces: `classify_change(before: str, after: str) -> str` (glyph-swap class for the report); CLI `--apply` (default dry-run), positional `artifact_ids` (default all).

- [ ] **Step 1: Write the failing test**

```python
# services/tests/scripts/test_reconcile_backfill_report.py
from scripts.reconcile_compound_labels import classify_change


def test_classify_single_glyph_swap():
    assert classify_change("CMX41O", "CMX410") == "O->0"


def test_classify_ignores_hyphen_and_case_formatting():
    assert classify_change("gsk-286", "GSK286") == "identical"


def test_classify_length_mismatch():
    assert classify_change("CMX41", "CMX410") == "format/length"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd services && uv run pytest tests/scripts/test_reconcile_backfill_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.reconcile_compound_labels'`.

- [ ] **Step 3: Write the script**

```python
# services/scripts/reconcile_compound_labels.py
"""Compound-label reconciliation backfill + blast-radius measurement.

Reconciles CSER-extracted compound labels against each document's own NER
compound_name tags, per artifact, via ReconcileCompoundLabelsUseCase. The fix is
applied at the aggregate source, so the running Temporal + read workers re-derive
BOTH the Mongo read model and the Qdrant compound vectors. No CSER, no GPU —
re-extraction is deliberately NOT used (deterministic OCR reproduces the same
wrong label).

--dry-run is the DEFAULT: it reports how many labels would change, by confusion
class, and writes NOTHING. Pass --apply to perform the reconciliation (requires
the workers running to propagate the emitted events, same as production).

Usage:
    uv run python scripts/reconcile_compound_labels.py                 # dry-run, all artifacts
    uv run python scripts/reconcile_compound_labels.py --apply         # apply, all artifacts
    uv run python scripts/reconcile_compound_labels.py <artifact_id>   # dry-run, one artifact
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from uuid import UUID

import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from returns.result import Success

from application.use_cases.reconcile_compound_labels_use_case import (
    ReconcileCompoundLabelsUseCase,
)
from infrastructure.config import settings
from infrastructure.di.container import create_container

logger = structlog.get_logger()


def classify_change(before: str, after: str) -> str:
    """Human-readable glyph-swap class for the dry-run report, e.g. 'O->0'."""
    b = before.strip().upper().replace("-", "").replace(" ", "")
    a = after.strip().upper().replace("-", "").replace(" ", "")
    if len(b) != len(a):
        return "format/length"
    swaps = sorted({f"{x}->{y}" for x, y in zip(b, a, strict=False) if x != y})
    return ",".join(swaps) or "identical"


async def _artifact_names_and_pages(db, artifact_id: UUID) -> tuple[list[str], list[UUID]]:
    """Per-artifact candidate names (NER compound_name tags, all pages) and the
    page_ids that carry compound_mentions — read from page_read_models."""
    names: list[str] = []
    page_ids: list[UUID] = []
    cursor = db[settings.mongo_pages_collection].find(
        {"artifact_id": str(artifact_id)},
        {"page_id": 1, "compound_mentions": 1, "tag_mentions": 1, "_id": 0},
    )
    async for doc in cursor:
        for tm in doc.get("tag_mentions") or []:
            if tm.get("entity_type") == "compound_name" and tm.get("tag"):
                names.append(tm["tag"])
        if doc.get("compound_mentions"):
            page_ids.append(UUID(doc["page_id"]))
    return names, page_ids


async def run(artifact_ids: list[str] | None, apply: bool) -> None:
    container = create_container()
    reconcile_uc = container[ReconcileCompoundLabelsUseCase]
    mongo = AsyncIOMotorClient(settings.mongo_uri)
    db = mongo[settings.mongo_db]

    try:
        if artifact_ids:
            ids = [UUID(a) for a in artifact_ids]
        else:
            ids = [
                UUID(doc.get("artifact_id") or str(doc["_id"]))
                async for doc in db[settings.mongo_artifacts_collection].find(
                    {}, {"_id": 1, "artifact_id": 1},
                )
            ]

        report: Counter[str] = Counter()
        total_changed = 0
        for aid in ids:
            names, page_ids = await _artifact_names_and_pages(db, aid)
            if not names or not page_ids:
                continue
            for pid in page_ids:
                result = await reconcile_uc.execute(
                    pid, candidate_names=names, dry_run=not apply,
                )
                if not isinstance(result, Success):
                    logger.warning("reconcile_failed", artifact_id=str(aid), page_id=str(pid))
                    continue
                dto = result.unwrap()
                for change in dto.changes:
                    report[classify_change(change.before, change.after)] += 1
                    total_changed += 1
                    logger.info(
                        "reconcile_change",
                        artifact_id=str(aid),
                        page_id=str(pid),
                        before=change.before,
                        after=change.after,
                        applied=dto.applied,
                    )

        mode = "APPLIED" if apply else "DRY-RUN (no writes)"
        logger.info(
            "reconcile_summary", mode=mode, total_changed=total_changed, by_class=dict(report),
        )
        print(f"\n=== {mode} ===")
        print(f"labels changed: {total_changed}")
        for cls, count in report.most_common():
            print(f"  {cls}: {count}")
    finally:
        mongo.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_ids", nargs="*", help="Artifact IDs (default: all artifacts)")
    parser.add_argument(
        "--apply", action="store_true", help="Apply changes (default: dry-run, no writes)",
    )
    args = parser.parse_args()
    asyncio.run(run(args.artifact_ids or None, apply=args.apply))
```

- [ ] **Step 4: Run the report test to verify it passes**

Run: `cd services && uv run pytest tests/scripts/test_reconcile_backfill_report.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Import-smoke the script**

Run: `cd services && uv run python -c "import scripts.reconcile_compound_labels"`
Expected: no output, exit 0.

- [ ] **Step 6: Commit**

```bash
git add services/scripts/reconcile_compound_labels.py services/tests/scripts/test_reconcile_backfill_report.py
git commit -m "feat(compounds): measure-first reconcile backfill script (--dry-run default)"
```

---

### Task 7: Docs fix + full suite green

**Files:**
- Modify: `services/design_docs/NER_PIPELINE.md` (stale entity name)

- [ ] **Step 1: Fix the stale NER entity name**

`design_docs/NER_PIPELINE.md` line ~22 lists the entity type as `compound` — the actual structflo TB profile emits `compound_name`. Change `compound` → `compound_name` in that entity-type list so it matches the code and this feature.

Run: `cd services && grep -n "compound" design_docs/NER_PIPELINE.md`
Confirm the entity-type table now reads `compound_name` (not a bare `compound`).

- [ ] **Step 2: Run the full backend test suite**

Run: `cd services && uv run pytest -q`
Expected: PASS — the pre-existing suite plus the new tests
(`tests/domain/test_compound_label_matcher.py`,
`tests/application/test_reconcile_compound_labels_use_case.py`,
`tests/application/test_trigger_compound_label_reconciliation.py`,
`tests/infrastructure/test_reconcile_compound_labels_activity.py`,
`tests/infrastructure/test_reconcile_container_wiring.py`,
`tests/scripts/test_reconcile_backfill_report.py`). Zero failures.

- [ ] **Step 3: Commit**

```bash
git add services/design_docs/NER_PIPELINE.md
git commit -m "docs(ner): correct compound_name entity type; finalize label reconciliation"
```

---

## Post-implementation (out of plan scope — human-gated)

1. **Run the measurement:** `uv run python scripts/reconcile_compound_labels.py` (dry-run, all artifacts) against a copy of prod data — or on ned with workers up. Read the by-class report: it is the blast-radius number.
2. **Decide the write-backfill** from that number. If worth it, run `--apply` (workers must be up so emitted events re-derive Qdrant + Mongo). Idempotent — safe to re-run.
3. **Ship** via `scripts/release.sh` (services component) and redeploy ned. The live path fixes new ingestions automatically.
4. **#1 remains** as the query-time safety net for the residual tail (reverse-race stragglers, no-NER-name pages). No action.

## Verification notes for the implementer

- The reconcile use case reads `page.compound_mentions` and `page.tag_mentions` and calls `page.update_compound_mentions(...)` — all confirmed on `domain/aggregates/page.py` (fields at :90–91, command at :113). It reuses the existing `CompoundMentionsUpdated` event; **no** new event, projector, transcoder, or Qdrant/Mongo write path is added (`CompoundMention` is already transcoder-registered at `container.py:200`).
- No changes to `CachingWorkflowOrchestrator` — it delegates `start_*` methods via `__getattr__` (`caching_orchestrator.py:42`).
- Cost note (intended): each correction causes one extra idempotent SMILES re-embed and one no-op reconcile pass (the reconciled `CompoundMentionsUpdated` re-enters both handlers). `SmilesEmbeddingGenerated` is terminal (not subscribed), so nothing loops back into NER/CSER.
