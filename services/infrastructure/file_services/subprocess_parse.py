"""Killable subprocess wrapper for document parsing.

Docling/MuPDF parse runs native code that can hang or segfault on pathological
PDFs; in-process it freezes the whole Temporal worker (2026-07-08 outage). Run
it in a child process the parent can kill, so a bad document just fails the
activity and Temporal's retry policy takes over.
"""

from __future__ import annotations

import multiprocessing
import pickle
import tempfile
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from application.ports.document_parser import DocumentParser

if TYPE_CHECKING:
    from application.dtos.parsed_document import ParseResult
    from application.ports.blob_store import BlobStore

log = structlog.get_logger(__name__)

# ponytail: result via temp-file pickle, not a Pipe — no pipe-buffer deadlock
# handling needed for multi-hundred-MB page images.


def _entry(result_path: str, target: Callable, args: tuple) -> None:
    try:
        out = ("ok", target(*args))
    except BaseException:
        out = ("err", traceback.format_exc())
    with Path(result_path).open("wb") as fh:
        pickle.dump(out, fh)


def run_in_subprocess(target: Callable, args: tuple, timeout_s: float) -> Any:
    """Run target(*args) in a spawned child; kill it if it exceeds timeout_s.

    target must be a module-level (picklable) callable. Raises TimeoutError on
    hang, RuntimeError on child exception or crash (e.g. segfault).
    """
    # spawn, not fork: the worker holds Temporal's Rust core threads — fork would deadlock.
    ctx = multiprocessing.get_context("spawn")
    with tempfile.TemporaryDirectory() as d:
        result_path = str(Path(d) / "result.pkl")
        p = ctx.Process(target=_entry, args=(result_path, target, args))
        p.start()
        p.join(timeout_s)
        if p.is_alive():
            p.kill()
            p.join()
            msg = f"parse subprocess exceeded {timeout_s}s — killed"
            raise TimeoutError(msg)
        if not Path(result_path).exists():
            msg = f"parse subprocess died without a result (exitcode={p.exitcode})"
            raise RuntimeError(msg)
        with Path(result_path).open("rb") as fh:
            # Trusted: written by our own spawned child into a private temp dir
            # this process created; never crosses a trust boundary.
            status, payload = pickle.load(fh)  # noqa: S301
    if status == "err":
        msg = f"parse subprocess failed:\n{payload}"
        raise RuntimeError(msg)
    return payload


def _docling_parse_path(path: str) -> ParseResult:
    """Child entry: fresh DoclingParser over a local file (models load per call)."""
    from infrastructure.file_services.docling_parser import DoclingParser

    return DoclingParser(blob_store=None).parse_path(Path(path))


class SubprocessParser(DocumentParser):
    """DocumentParser that runs the Docling parse in a killable child process."""

    def __init__(
        self,
        blob_store: BlobStore,
        timeout_s: float = 1500,  # < the activity's 30-min start_to_close
        child: Callable[[str], ParseResult] = _docling_parse_path,
    ) -> None:
        self.blob_store = blob_store
        self.timeout_s = timeout_s
        self.child = child

    def parse(self, storage_key: str) -> ParseResult:
        with self.blob_store.get_file(storage_key) as path:
            result = run_in_subprocess(self.child, (str(path),), self.timeout_s)
        log.info("subprocess_parse.done", storage_key=storage_key, pages=len(result.pages))
        return result
