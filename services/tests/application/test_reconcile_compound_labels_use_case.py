import asyncio
from uuid import uuid4

from returns.result import Success

from application.use_cases.reconcile_compound_labels_use_case import (
    ReconcileCompoundLabelsUseCase,
)
from domain.value_objects.compound_mention import CompoundMention
from domain.value_objects.tag_mention import TagMention


class FakePage:
    def __init__(
        self,
        page_id,
        artifact_id,
        compound_mentions,
        tag_mentions,
        human_corrections=None,
    ):
        self.id = page_id
        self.artifact_id = artifact_id
        self.workspace_id = None
        self.compound_mentions = compound_mentions
        self.tag_mentions = tag_mentions
        self.human_corrections = human_corrections or {}
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


def _page_with(cser_label, ner_name, human_corrections=None):
    return FakePage(
        page_id=uuid4(),
        artifact_id=uuid4(),
        compound_mentions=[
            CompoundMention(
                smiles="C",
                canonical_smiles="C",
                is_smiles_valid=True,
                extracted_id=cser_label,
            ),
        ],
        tag_mentions=([TagMention(tag=ner_name, entity_type="compound_name")] if ner_name else []),
        human_corrections=human_corrections,
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


def test_human_corrected_page_reports_pending_but_not_applied():
    # A human owns this page's compounds — a pending relabel must be reported
    # honestly (in `changes`) but NOT applied, and the repo must not be saved.
    page = _page_with(
        "CMX41O",
        "CMX410",
        human_corrections={"compound_mentions": {"corrected_by_id": "u1"}},
    )
    repo = FakeRepo(page)
    uc = ReconcileCompoundLabelsUseCase(page_repository=repo)

    dto = asyncio.run(uc.execute(page.id)).unwrap()

    assert dto.applied is False
    assert [(c.before, c.after) for c in dto.changes] == [("CMX41O", "CMX410")]
    assert page.updated_with is None  # mutation skipped
    assert repo.saved is False  # not saved → no events emitted


def test_dry_run_reports_changes_without_saving():
    page = _page_with("CMX41O", "CMX410")
    repo = FakeRepo(page)
    uc = ReconcileCompoundLabelsUseCase(page_repository=repo)

    dto = asyncio.run(uc.execute(page.id, candidate_names=["CMX410"], dry_run=True)).unwrap()

    assert dto.applied is False
    assert [(c.before, c.after) for c in dto.changes] == [("CMX41O", "CMX410")]
    assert page.updated_with is None
    assert repo.saved is False
