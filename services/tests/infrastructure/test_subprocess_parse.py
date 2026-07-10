"""Tests for the killable subprocess parse runner.

Child functions must be module-level so multiprocessing spawn can pickle them.
"""

import contextlib
import os
import tempfile
import time
from pathlib import Path

import pytest

from application.dtos.parsed_document import ParsedDocument, ParseResult
from infrastructure.file_services.subprocess_parse import (
    SubprocessParser,
    run_in_subprocess,
)


def _child_ok(x):
    return x * 2


def _child_sleeps(_x):
    time.sleep(60)


def _child_raises(_x):
    msg = "bad pdf: boom"
    raise ValueError(msg)


def _child_dies(_x):
    os._exit(1)  # simulates a native crash (segfault) — no result written


def _child_parse(path):
    return ParseResult(
        document=ParsedDocument(source_mime="application/pdf", blocks=[]),
        pages=[],
    )


def test_run_in_subprocess_returns_result():
    assert run_in_subprocess(_child_ok, (21,), timeout_s=30) == 42


def test_run_in_subprocess_kills_on_timeout():
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        run_in_subprocess(_child_sleeps, (0,), timeout_s=2)
    assert time.monotonic() - start < 30  # killed, not waited out


def test_run_in_subprocess_propagates_child_exception():
    with pytest.raises(RuntimeError, match="bad pdf: boom"):
        run_in_subprocess(_child_raises, (0,), timeout_s=30)


def test_run_in_subprocess_raises_on_child_crash():
    with pytest.raises(RuntimeError, match="exitcode"):
        run_in_subprocess(_child_dies, (0,), timeout_s=30)


class FakeBlob:
    def __init__(self):
        self.sources: dict[str, bytes] = {}

    @contextlib.contextmanager
    def get_file(self, key):
        d = tempfile.mkdtemp()
        p = os.path.join(d, os.path.basename(key))
        Path(p).write_bytes(self.sources[key])
        yield Path(p)


def test_subprocess_parser_parses_via_child():
    blob = FakeBlob()
    blob.sources["artifacts/x/render.pdf"] = b"%PDF-1.4 fake"
    parser = SubprocessParser(blob_store=blob, timeout_s=30, child=_child_parse)

    result = parser.parse("artifacts/x/render.pdf")

    assert result.document.source_mime == "application/pdf"
    assert result.pages == []
