"""LibreOffice-backed Office→PDF converter.

Renders Office documents (PPTX, DOCX, …) to PDF so they flow through the one PDF
ingestion pipeline (Docling parse, page images, CSER, doc-metadata).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from application.ports.office_converter import OfficeToPdfConverter
from domain.value_objects.mime_type import MimeType

if TYPE_CHECKING:
    from application.ports.blob_store import BlobStore

log = structlog.get_logger(__name__)

# macOS app bundle path is not on PATH; check it explicitly for local dev.
_MAC_SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"

# The only variables soffice inherits. The worker's environment holds API keys
# and DB credentials, and a crafted document must not be able to read them
# (cf. CVE-2024-12426, which expanded env vars into the output).
_SOFFICE_ENV = ("PATH", "HOME", "LANG")


# Per-process caps for soffice: CPU at the wall-clock timeout, address space and
# written-file size so a decompression bomb dies instead of eating the worker.
_SOFFICE_AS_BYTES = 4 * 2**30
_SOFFICE_FSIZE_BYTES = 2**30


# LibreOffice picks an importer by sniffing content, so a renamed ODT, RTF or PDF
# would reach other import filters. Force the one the upload was verified as.
_IMPORT_FILTERS = {
    MimeType.DOCX: "MS Word 2007 XML",
    MimeType.PPTX: "Impress MS PowerPoint 2007 XML",
}


def _setting(path: str, name: str, value: str) -> str:
    return (
        f'<item oor:path="{path}"><prop oor:name="{name}" oor:op="fuse">'
        f"<value>{value}</value></prop></item>"
    )


_SCRIPTING = "/org.openoffice.Office.Common/Security/Scripting"
# Seeded into every fresh profile: linked content (file://, http://) is never
# loaded (the setting Gotenberg ships), and macros, OLE and DDE are off.
_PROFILE_SETTINGS = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<oor:items xmlns:oor="http://openoffice.org/2001/registry"'
    ' xmlns:xs="http://www.w3.org/2001/XMLSchema"'
    ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
    + _setting(_SCRIPTING, "BlockUntrustedRefererLinks", "true")
    + _setting(_SCRIPTING, "DisableMacrosExecution", "true")
    + _setting(_SCRIPTING, "MacroSecurityLevel", "3")
    + _setting(_SCRIPTING, "DisableActiveContent", "true")
    + _setting("/org.openoffice.Office.Writer/Content/Update", "Link", "0")  # never
    + _setting("/org.openoffice.Office.Writer/Content/Update", "Field", "false")
    + _setting("/org.openoffice.Office.Writer/Content/Update", "Chart", "false")
    + _setting("/org.openoffice.Office.Writer/Filter/Import/VBA", "Load", "false")
    + _setting("/org.openoffice.Office.Writer/Filter/Import/VBA", "Executable", "false")
    + _setting("/org.openoffice.Office.Impress/Filter/Import/VBA", "Load", "false")
    + "</oor:items>"
)


def find_soffice() -> str | None:
    """Path to the LibreOffice headless binary, or None if not installed."""
    return shutil.which("soffice") or shutil.which("libreoffice") or (
        _MAC_SOFFICE if Path(_MAC_SOFFICE).exists() else None
    )


class LibreOfficeConverter(OfficeToPdfConverter):
    def __init__(
        self,
        blob_store: BlobStore,
        soffice_bin: str | None = None,
        timeout_s: int = 180,
    ) -> None:
        self.blob_store = blob_store
        self.soffice_bin = soffice_bin or find_soffice()
        self.timeout_s = timeout_s

    def convert_to_pdf(
        self, source_storage_key: str, dest_storage_key: str, mime_type: MimeType
    ) -> None:
        if not self.soffice_bin:
            msg = "LibreOffice (soffice) not found — cannot convert Office documents to PDF"
            raise RuntimeError(msg)

        with self.blob_store.get_file(source_storage_key) as src_path:
            src_path = Path(src_path)
            with tempfile.TemporaryDirectory() as outdir:
                self._run(src_path, outdir, _IMPORT_FILTERS[mime_type])
                # LibreOffice names the output <input-stem>.pdf in --outdir.
                pdf_path = Path(outdir) / f"{src_path.stem}.pdf"
                if not pdf_path.exists():
                    msg = f"LibreOffice produced no PDF for {source_storage_key}"
                    raise RuntimeError(msg)
                with pdf_path.open("rb") as fh:
                    self.blob_store.put_stream(
                        dest_storage_key, fh, mime_type="application/pdf"
                    )
        log.info("libreoffice.converted", source=source_storage_key, dest=dest_storage_key)

    def _run(self, src_path: Path, outdir: str, infilter: str) -> None:
        # ponytail: unique per-call UserInstallation profile — without it, parallel
        # soffice invocations collide on the shared profile lock and silently fail.
        profile = Path(outdir) / "profile"
        (profile / "user").mkdir(parents=True)
        (profile / "user" / "registrymodifications.xcu").write_text(_PROFILE_SETTINGS)
        # prlimit (util-linux) applies rlimits before exec. preexec_fn would do it
        # in Python but is unsafe in this multi-threaded worker. Absent on macOS dev.
        prlimit = shutil.which("prlimit")
        limits = (
            [
                prlimit,
                f"--cpu={self.timeout_s}",
                f"--as={_SOFFICE_AS_BYTES}",
                f"--fsize={_SOFFICE_FSIZE_BYTES}",
                "--",
            ]
            if prlimit
            else []
        )
        # Safe: fixed binary + literal flags + paths we created; no shell, no user input.
        subprocess.run(  # noqa: S603
            [
                *limits,
                self.soffice_bin,
                "--headless",
                f"-env:UserInstallation=file://{profile}",
                f"--infilter={infilter}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(outdir),
                str(src_path),
            ],
            check=True,
            timeout=self.timeout_s,
            capture_output=True,
            env={k: os.environ[k] for k in _SOFFICE_ENV if k in os.environ},
        )
