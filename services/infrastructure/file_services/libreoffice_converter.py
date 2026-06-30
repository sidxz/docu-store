"""LibreOffice-backed Office→PDF converter.

Renders Office documents (PPTX, DOCX, …) to PDF so they flow through the one PDF
ingestion pipeline (Docling parse, page images, CSER, doc-metadata).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from application.ports.office_converter import OfficeToPdfConverter

if TYPE_CHECKING:
    from application.ports.blob_store import BlobStore

log = structlog.get_logger(__name__)

# macOS app bundle path is not on PATH; check it explicitly for local dev.
_MAC_SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"


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

    def convert_to_pdf(self, source_storage_key: str, dest_storage_key: str) -> None:
        if not self.soffice_bin:
            msg = "LibreOffice (soffice) not found — cannot convert Office documents to PDF"
            raise RuntimeError(msg)

        with self.blob_store.get_file(source_storage_key) as src_path:
            src_path = Path(src_path)
            with tempfile.TemporaryDirectory() as outdir:
                self._run(src_path, outdir)
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

    def _run(self, src_path: Path, outdir: str) -> None:
        # ponytail: unique per-call UserInstallation profile — without it, parallel
        # soffice invocations collide on the shared profile lock and silently fail.
        profile = Path(outdir) / "profile"
        # Safe: fixed binary + literal flags + paths we created; no shell, no user input.
        subprocess.run(  # noqa: S603
            [
                self.soffice_bin,
                "--headless",
                f"-env:UserInstallation=file://{profile}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(outdir),
                str(src_path),
            ],
            check=True,
            timeout=self.timeout_s,
            capture_output=True,
        )
