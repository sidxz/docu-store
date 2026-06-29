#!/usr/bin/env python3
"""Docling vs PyMuPDF extraction comparison harness (Phase-0 quality gate).

Compares text and page extraction between Docling and PyMuPDF on a corpus of PDFs.
Run against representative scientific PDFs before cutting over to Docling (Phase 1).

Usage:
    uv run python scripts/docling_vs_pymupdf.py tests/fixtures/corpus
    uv run python scripts/docling_vs_pymupdf.py tests/fixtures
"""
from __future__ import annotations

import argparse
import io
import sys
import tempfile
from pathlib import Path

# Ensure services directory is in the path for imports
services_dir = Path(__file__).parent.parent
if str(services_dir) not in sys.path:
    sys.path.insert(0, str(services_dir))

from infrastructure.blob_stores.fsspec_blob_store import FsspecBlobStore
from infrastructure.file_services.docling_parser import DoclingParser
from infrastructure.file_services.py_mu_pfd_service import PyMuPDFService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare Docling vs PyMuPDF text/page extraction on a PDF corpus."
    )
    parser.add_argument(
        "corpus_dir",
        nargs="?",
        default="tests/fixtures/corpus",
        help="Directory containing PDF files to compare (default: %(default)s)",
    )
    args = parser.parse_args()

    corpus_path = Path(args.corpus_dir)
    pdfs = sorted(corpus_path.glob("*.pdf"))

    if not pdfs:
        print(f"No PDFs found in {corpus_path}. Pass a directory of scientific PDFs to compare.")
        return 0

    # Create temporary blob store
    with tempfile.TemporaryDirectory() as tmp_dir:
        blob_store = FsspecBlobStore(base_url=f"file://{tmp_dir}")
        docling = DoclingParser(blob_store)
        pymupdf = PyMuPDFService(blob_store)

        for pdf_path in pdfs:
            pdf_bytes = pdf_path.read_bytes()
            key = f"artifacts/{pdf_path.stem}/source.pdf"

            # Write to blob store
            blob_store.put_stream(
                key, io.BytesIO(pdf_bytes), mime_type="application/pdf"
            )

            # Parse with both parsers
            docling_result = docling.parse(key)
            pymupdf_result = pymupdf.parse(storage_key=key)

            # Extract metrics
            docling_pages = len(docling_result.pages)
            docling_chars = sum(len(b.text) for b in docling_result.document.blocks)

            pymupdf_pages = len(pymupdf_result.pages or [])
            pymupdf_chars = len(pymupdf_result.combined_content or "")

            # Print comparison
            print(
                f"{pdf_path.name}: docling_pages={docling_pages} pymupdf_pages={pymupdf_pages} "
                f"docling_chars={docling_chars} pymupdf_chars={pymupdf_chars}"
            )

    return 0


if __name__ == "__main__":
    exit(main())
