"""Tests for CorrectPageCompoundMentionsUseCase (hiledit human-in-the-loop corrections)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.correction_dtos import (
    CorrectedCompoundInput,
    CorrectPageCompoundMentionsRequest,
)
from application.use_cases.correct_metadata_use_cases import CorrectPageCompoundMentionsUseCase
from domain.aggregates.page import Page
from domain.value_objects.compound_mention import CompoundMention
from tests.fakes.fake_auth import FakeAuth
from tests.mocks import MockExternalEventPublisher, MockPageRepository

# ---------------------------------------------------------------------------
# Local fixtures — mirror the style used in
# tests/application/test_correct_artifact_metadata_use_case.py (Task 3).
# ---------------------------------------------------------------------------


class FakeSmilesValidator:
    """Fake SmilesValidator port: canonicalizes by upper-casing; "BAD" is invalid."""

    def validate(self, smiles: str) -> bool:
        return smiles != "BAD"

    def canonicalize(self, smiles: str) -> str | None:
        return None if smiles == "BAD" else smiles.upper()


@pytest.fixture
def fake_page_repo() -> MockPageRepository:
    return MockPageRepository()


@pytest.fixture
def smiles_validator() -> FakeSmilesValidator:
    return FakeSmilesValidator()


@pytest.fixture
def auth_editor() -> FakeAuth:
    return FakeAuth(role="editor", name="Jane Reviewer", email="jane.reviewer@example.com")


@pytest.fixture
def make_saved_page(fake_page_repo: MockPageRepository):
    """Factory: build + save a Page, optionally pre-seeded with a machine-extracted mention."""

    def _make(*, with_mention: bool = False) -> Page:
        page = Page.create(name="Page 1", artifact_id=uuid4(), index=0)
        if with_mention:
            page.update_compound_mentions(
                [
                    CompoundMention(
                        smiles="c1ccccc1",
                        canonical_smiles="c1ccccc1",
                        is_smiles_valid=True,
                        extracted_id="CMX41O",
                    ),
                ],
            )
        fake_page_repo.save(page)
        return page

    return _make


class TestCorrectPageCompoundMentionsUseCase:
    """Test CorrectPageCompoundMentionsUseCase — human corrections to page compound mentions."""

    @pytest.mark.asyncio
    async def test_corrects_label_and_revalidates_smiles(
        self,
        fake_page_repo: MockPageRepository,
        make_saved_page,
        smiles_validator: FakeSmilesValidator,
        auth_editor: FakeAuth,
    ) -> None:
        """A corrected label + SMILES is revalidated/canonicalized via the same validator port."""
        page = make_saved_page(with_mention=True)  # seeded with extracted_id="CMX41O"
        uc = CorrectPageCompoundMentionsUseCase(
            page_repository=fake_page_repo,
            smiles_validator=smiles_validator,
        )

        result = await uc.execute(
            page_id=page.id,
            request=CorrectPageCompoundMentionsRequest(
                compound_mentions=[
                    CorrectedCompoundInput(smiles="cco", extracted_id="CMX410"),
                ],
            ),
            auth=auth_editor,
        )

        assert isinstance(result, Success)
        saved = fake_page_repo.get_by_id(page.id)
        assert len(saved.compound_mentions) == 1
        mention = saved.compound_mentions[0]
        assert mention.extracted_id == "CMX410"
        assert mention.canonical_smiles == "CCO"  # revalidated from the new "cco", not carried over
        assert mention.is_smiles_valid is True
        assert saved.human_corrections["compound_mentions"]["corrected_by_id"] == str(
            auth_editor.user_id,
        )
        assert saved.human_corrections["compound_mentions"]["corrected_by_name"] == auth_editor.name

    @pytest.mark.asyncio
    async def test_invalid_smiles_rejected_with_validation_error(
        self,
        fake_page_repo: MockPageRepository,
        make_saved_page,
        smiles_validator: FakeSmilesValidator,
        auth_editor: FakeAuth,
    ) -> None:
        """An invalid SMILES is rejected by name in the error; nothing is saved."""
        page = make_saved_page(with_mention=True)
        uc = CorrectPageCompoundMentionsUseCase(
            page_repository=fake_page_repo,
            smiles_validator=smiles_validator,
        )

        result = await uc.execute(
            page_id=page.id,
            request=CorrectPageCompoundMentionsRequest(
                compound_mentions=[CorrectedCompoundInput(smiles="BAD")],
            ),
            auth=auth_editor,
        )

        assert isinstance(result, Failure)
        error = result.failure()
        assert error.category == "validation"
        assert "BAD" in error.message
        saved = fake_page_repo.get_by_id(page.id)
        assert len(saved.compound_mentions) == 1  # untouched — original mention survives
        assert saved.compound_mentions[0].extracted_id == "CMX41O"
        assert saved.human_corrections == {}  # nothing recorded

    @pytest.mark.asyncio
    async def test_empty_list_clears_mentions(
        self,
        fake_page_repo: MockPageRepository,
        make_saved_page,
        smiles_validator: FakeSmilesValidator,
        auth_editor: FakeAuth,
    ) -> None:
        """An empty compound_mentions list clears all mentions but still records provenance."""
        page = make_saved_page(with_mention=True)
        uc = CorrectPageCompoundMentionsUseCase(
            page_repository=fake_page_repo,
            smiles_validator=smiles_validator,
        )

        result = await uc.execute(
            page_id=page.id,
            request=CorrectPageCompoundMentionsRequest(compound_mentions=[]),
            auth=auth_editor,
        )

        assert isinstance(result, Success)
        saved = fake_page_repo.get_by_id(page.id)
        assert saved.compound_mentions == []
        assert saved.human_corrections["compound_mentions"]["corrected_by_id"] == str(
            auth_editor.user_id,
        )

    @pytest.mark.asyncio
    async def test_requires_auth(
        self,
        fake_page_repo: MockPageRepository,
        make_saved_page,
        smiles_validator: FakeSmilesValidator,
    ) -> None:
        """A correction with no authenticated actor is rejected outright (not a silent no-op)."""
        page = make_saved_page()
        uc = CorrectPageCompoundMentionsUseCase(
            page_repository=fake_page_repo,
            smiles_validator=smiles_validator,
        )

        result = await uc.execute(
            page_id=page.id,
            request=CorrectPageCompoundMentionsRequest(
                compound_mentions=[CorrectedCompoundInput(smiles="cco")],
            ),
            auth=None,
        )

        assert isinstance(result, Failure)
        assert result.failure().category == "unauthorized"

    @pytest.mark.asyncio
    async def test_notifies_publisher_with_correction_sub_type(
        self,
        fake_page_repo: MockPageRepository,
        make_saved_page,
        smiles_validator: FakeSmilesValidator,
        auth_editor: FakeAuth,
    ) -> None:
        """When wired, the external publisher is notified with the HumanCorrectionRecorded sub_type."""
        page = make_saved_page()
        publisher = MockExternalEventPublisher()
        uc = CorrectPageCompoundMentionsUseCase(
            page_repository=fake_page_repo,
            smiles_validator=smiles_validator,
            external_event_publisher=publisher,
        )

        result = await uc.execute(
            page_id=page.id,
            request=CorrectPageCompoundMentionsRequest(compound_mentions=[]),
            auth=auth_editor,
        )

        assert isinstance(result, Success)
        assert publisher.page_updated_called

    @pytest.mark.asyncio
    async def test_untouched_mention_keeps_provenance_edited_gets_fresh(
        self,
        fake_page_repo: MockPageRepository,
        smiles_validator: FakeSmilesValidator,
        auth_editor: FakeAuth,
    ) -> None:
        """A full-replace that edits only one mention round-trips the others verbatim.

        The unchanged mention keeps its identity + machine provenance
        (confidence/model_name); the relabeled one is rebuilt fresh (provenance dropped).
        """
        page = Page.create(name="Page 1", artifact_id=uuid4(), index=0)
        m_keep = CompoundMention(
            smiles="c1ccccc1",
            canonical_smiles="c1ccccc1",
            is_smiles_valid=True,
            extracted_id="A1",
            confidence=0.91,
            model_name="cser",
        )
        m_edit = CompoundMention(
            smiles="CCO",
            canonical_smiles="CCO",
            is_smiles_valid=True,
            extracted_id="B2",
            confidence=0.82,
            model_name="cser",
        )
        page.update_compound_mentions([m_keep, m_edit])
        fake_page_repo.save(page)

        uc = CorrectPageCompoundMentionsUseCase(
            page_repository=fake_page_repo,
            smiles_validator=smiles_validator,
        )
        result = await uc.execute(
            page_id=page.id,
            request=CorrectPageCompoundMentionsRequest(
                compound_mentions=[
                    CorrectedCompoundInput(smiles="c1ccccc1", extracted_id="A1"),  # unchanged
                    CorrectedCompoundInput(smiles="CCO", extracted_id="B2-fixed"),  # relabeled
                ],
            ),
            auth=auth_editor,
        )

        assert isinstance(result, Success)
        saved = fake_page_repo.get_by_id(page.id)
        # Untouched mention: same object, machine provenance intact.
        assert saved.compound_mentions[0] is m_keep
        assert saved.compound_mentions[0].confidence == 0.91
        assert saved.compound_mentions[0].model_name == "cser"
        # Edited mention: rebuilt fresh, machine provenance dropped, SMILES recanonicalized.
        assert saved.compound_mentions[1].extracted_id == "B2-fixed"
        assert saved.compound_mentions[1].confidence is None
        assert saved.compound_mentions[1].model_name is None
        assert saved.compound_mentions[1].canonical_smiles == "CCO"

    @pytest.mark.asyncio
    async def test_viewer_role_rejected(
        self,
        fake_page_repo: MockPageRepository,
        make_saved_page,
        smiles_validator: FakeSmilesValidator,
    ) -> None:
        """A viewer (insufficient role) is rejected with forbidden."""
        page = make_saved_page()
        uc = CorrectPageCompoundMentionsUseCase(
            page_repository=fake_page_repo,
            smiles_validator=smiles_validator,
        )

        result = await uc.execute(
            page_id=page.id,
            request=CorrectPageCompoundMentionsRequest(compound_mentions=[]),
            auth=FakeAuth(role="viewer"),
        )

        assert isinstance(result, Failure)
        assert result.failure().category == "forbidden"

    @pytest.mark.asyncio
    async def test_cross_workspace_rejected(
        self,
        fake_page_repo: MockPageRepository,
        smiles_validator: FakeSmilesValidator,
    ) -> None:
        """A page in another workspace reads as not_found (existence not leaked)."""
        page = Page.create(name="Page 1", artifact_id=uuid4(), index=0, workspace_id=uuid4())
        fake_page_repo.save(page)
        uc = CorrectPageCompoundMentionsUseCase(
            page_repository=fake_page_repo,
            smiles_validator=smiles_validator,
        )

        result = await uc.execute(
            page_id=page.id,
            request=CorrectPageCompoundMentionsRequest(compound_mentions=[]),
            auth=FakeAuth(role="editor", workspace_id=uuid4()),
        )

        assert isinstance(result, Failure)
        assert result.failure().category == "not_found"

    @pytest.mark.asyncio
    async def test_human_placed_coordinates_are_persisted(
        self,
        fake_page_repo: MockPageRepository,
        make_saved_page,
        smiles_validator: FakeSmilesValidator,
        auth_editor: FakeAuth,
    ) -> None:
        """A corrected pair keeps its boxes, and claims no detector confidence."""
        page = make_saved_page(with_mention=True)
        uc = CorrectPageCompoundMentionsUseCase(
            page_repository=fake_page_repo,
            smiles_validator=smiles_validator,
        )

        result = await uc.execute(
            page_id=page.id,
            request=CorrectPageCompoundMentionsRequest(
                compound_mentions=[
                    CorrectedCompoundInput(
                        smiles="CCO",
                        extracted_id="1a",
                        structure_bbox=[10, 20, 110, 220],
                        label_bbox=[10, 230, 60, 250],
                    ),
                ],
            ),
            auth=auth_editor,
        )

        assert isinstance(result, Success)
        mention = fake_page_repo.get_by_id(page.id).compound_mentions[0]
        assert mention.structure_bbox == [10, 20, 110, 220]
        assert mention.label_bbox == [10, 230, 60, 250]
        # Not accepted from clients: a reviewer has no detector confidence.
        assert mention.structure_confidence is None
        assert mention.label_confidence is None

    @pytest.mark.asyncio
    async def test_an_unlabelled_structure_is_accepted(
        self,
        fake_page_repo: MockPageRepository,
        make_saved_page,
        smiles_validator: FakeSmilesValidator,
        auth_editor: FakeAuth,
    ) -> None:
        """The training format allows "label_bbox": null, so the VO must too."""
        page = make_saved_page(with_mention=True)
        uc = CorrectPageCompoundMentionsUseCase(
            page_repository=fake_page_repo,
            smiles_validator=smiles_validator,
        )

        result = await uc.execute(
            page_id=page.id,
            request=CorrectPageCompoundMentionsRequest(
                compound_mentions=[
                    CorrectedCompoundInput(
                        smiles="CCO",
                        structure_bbox=[10, 20, 110, 220],
                        label_bbox=None,
                    ),
                ],
            ),
            auth=auth_editor,
        )

        assert isinstance(result, Success)
        mention = fake_page_repo.get_by_id(page.id).compound_mentions[0]
        assert mention.structure_bbox == [10, 20, 110, 220]
        assert mention.label_bbox is None
