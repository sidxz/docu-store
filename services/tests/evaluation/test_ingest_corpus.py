"""ingest_corpus must refuse to upload a human deck it cannot name.

A miss in the anchor map (a PDF added before MERGED_GOLD was regenerated, a
rename, a stale gold JSON) must fail loud and before any upload starts — not
silently fall back to the DECK-PMC... filename this task exists to remove.
chembl_gold must keep naming by pdf.stem with no lookup and no new failure mode.
"""

import sys
from pathlib import Path

import pytest

from evaluation import ingest_corpus


def test_artifact_name_returns_stem_when_no_anchors():
    # chembl_gold path: empty anchors dict, no lookup, can never fail.
    assert ingest_corpus.artifact_name(Path("PMC123.pdf"), {}) == "PMC123"


def test_artifact_name_returns_the_anchor_when_present():
    anchors = {"DECK-PMC1": "a real deck title"}
    assert ingest_corpus.artifact_name(Path("DECK-PMC1.pdf"), anchors) == "a real deck title"


def test_artifact_name_fails_loud_on_a_miss():
    with pytest.raises(KeyError):
        ingest_corpus.artifact_name(Path("DECK-DRIFTED.pdf"), {"DECK-OTHER": "x"})


def test_main_aborts_before_any_upload_on_unresolved_anchor(tmp_path, monkeypatch, capsys):
    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    (pdf_dir / "DECK-DRIFTED.pdf").write_bytes(b"%PDF-1.4")

    # A stale anchor map: it knows about some other deck, not this one.
    monkeypatch.setattr(ingest_corpus, "human_deck_anchors", lambda: {"DECK-OTHER": "some title"})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest_corpus.py",
            "--api", "http://example.invalid",  # never dialed if the gate works
            "--workspace", "ws",
            "--corpus", "chembl_decks_human",
            "--pdf-dir", str(pdf_dir),
            "--out", str(tmp_path / "binding.json"),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        ingest_corpus.main()

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "DECK-DRIFTED.pdf" in err
    assert "no anchor" in err
