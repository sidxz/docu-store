"""Tests for human-in-the-loop compound-mention corrections on the Page aggregate."""

from __future__ import annotations

from uuid import uuid4

import pytest

from domain.aggregates.page import Page
from domain.value_objects.compound_mention import CompoundMention


class TestPageCompoundMentionCorrections:
    """Test correct_compound_mentions: provenance recording + machine-update guard."""

    @staticmethod
    def _cm(smiles: str, extracted_id: str | None = None) -> CompoundMention:
        return CompoundMention(
            smiles=smiles,
            canonical_smiles=smiles,
            is_smiles_valid=True,
            extracted_id=extracted_id,
        )

    def test_records_provenance_and_replaces_list(self) -> None:
        """Test that correction replaces compound_mentions and records provenance atomically."""
        page = Page.create(name="page-1", artifact_id=uuid4(), index=0, workspace_id=uuid4())
        page.update_compound_mentions([self._cm("CCO", "CMX41O")])
        page.correct_compound_mentions(
            [self._cm("CCO", "CMX410")],
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

    def test_machine_update_skipped_after_correction(self, sample_page: Page) -> None:
        """Test that a subsequent machine update (e.g. CSER/reconcile) is silently skipped."""
        sample_page.correct_compound_mentions(
            [self._cm("CCO")],
            corrected_by_id="u-1",
            corrected_by_name=None,
        )
        sample_page.update_compound_mentions([self._cm("CCC")])  # CSER/reconcile path — no-op
        assert sample_page.compound_mentions[0].smiles == "CCO"

    def test_rejected_on_deleted_page(self, sample_page: Page) -> None:
        """Test that correcting compound mentions on a deleted page raises."""
        sample_page.delete()
        with pytest.raises(ValueError, match="deleted"):
            sample_page.correct_compound_mentions(
                [self._cm("CCO")],
                corrected_by_id="u",
                corrected_by_name=None,
            )

    def test_replay_reconstructs_guard_state(self, sample_page: Page) -> None:
        """Test that replaying events from scratch reconstructs the correction guard."""
        sample_page.correct_compound_mentions(
            [self._cm("CCO")],
            corrected_by_id="u-1",
            corrected_by_name=None,
        )
        events = sample_page.collect_events()
        replayed = None
        for e in events:
            replayed = e.mutate(replayed)
        replayed.update_compound_mentions([self._cm("CCC")])
        assert replayed.compound_mentions[0].smiles == "CCO"
