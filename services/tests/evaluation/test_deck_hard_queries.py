"""The shipped hard query set must not be regenerable by accident.

Its 333 questions are worded by hand, 31 were removed for having no single right
answer, and H5 lists its compounds in an order varied per question — the fixed
rotation it replaced made that whole capability solvable without reading a slide.
None of that survives a regeneration, and there is no source file to rebuild it
from, so `deck_hard_queries` has to refuse unless asked twice.
"""

import json
import sys

import pytest

from evaluation import deck_hard_queries


def _argv(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["deck_hard_queries.py", *args])


def test_refuses_to_overwrite_an_existing_query_set(tmp_path, monkeypatch):
    out = tmp_path / "deck_queries_hard.json"
    out.write_text(json.dumps({"queries": [{"query_id": "HAND-0001"}]}))

    _argv(monkeypatch, "--out", str(out))
    with pytest.raises(SystemExit) as exc:
        deck_hard_queries.main()

    assert exc.value.code != 0
    assert "refusing to overwrite" in str(exc.value)
    # the hand-written content is still there
    assert json.loads(out.read_text())["queries"][0]["query_id"] == "HAND-0001"


def test_the_refusal_names_the_ways_out(tmp_path, monkeypatch):
    out = tmp_path / "deck_queries_hard.json"
    out.write_text("{}")

    _argv(monkeypatch, "--out", str(out))
    with pytest.raises(SystemExit) as exc:
        deck_hard_queries.main()

    message = str(exc.value)
    for escape_hatch in ("--verify", "--out", "--force"):
        assert escape_hatch in message


def test_writing_to_a_fresh_path_is_not_blocked(tmp_path, monkeypatch):
    # The guard is about clobbering, not about generating.
    out = tmp_path / "somewhere-new.json"
    _argv(monkeypatch, "--out", str(out))

    deck_hard_queries.main()

    assert out.exists()
    assert json.loads(out.read_text())["queries"]
