"""Bulk upload PDFs from a directory to docu-store."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from scripts.cli.auth import CliAuth


def get_existing_filenames(client: httpx.Client, api_url: str) -> set[str]:
    """Fetch all existing artifact filenames for --resume support."""
    filenames: set[str] = set()
    skip = 0
    limit = 100
    while True:
        resp = client.get(f"{api_url}/artifacts", params={"skip": skip, "limit": limit})
        resp.raise_for_status()
        artifacts = resp.json()
        if not artifacts:
            break
        for a in artifacts:
            if a.get("source_filename"):
                filenames.add(a["source_filename"])
        if len(artifacts) < limit:
            break
        skip += limit
    return filenames


def upload_directory(
    auth: CliAuth,
    directory: Path,
    api_url: str,
    artifact_type: str = "RESEARCH_ARTICLE",
    visibility: str = "workspace",
    delay: float = 2.0,
    dry_run: bool = False,
    resume: bool = False,
    recursive: bool = False,
) -> None:
    """Upload all PDFs from a directory."""
    if not directory.is_dir():
        print(f"Error: {directory} is not a directory", file=sys.stderr)
        sys.exit(1)

    pattern = "**/*.pdf" if recursive else "*.pdf"
    pdf_files = sorted(directory.glob(pattern))
    if not pdf_files:
        print(f"No PDF files found in {directory}")
        sys.exit(0)

    print(f"Found {len(pdf_files)} PDF files in {directory}")

    if dry_run:
        for i, f in enumerate(pdf_files, 1):
            rel = f.relative_to(directory)
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  [{i}/{len(pdf_files)}] {rel} ({size_mb:.1f} MB)")
        print(f"\nDry run complete. {len(pdf_files)} files would be uploaded.")
        return

    # Auth is auto-managed — get_headers() refreshes the token if needed
    client = httpx.Client(timeout=300)

    skip_filenames: set[str] = set()
    if resume:
        print("Checking for already-uploaded files...")
        client.headers.update(auth.get_headers())
        skip_filenames = get_existing_filenames(client, api_url)
        print(f"  Found {len(skip_filenames)} existing artifacts")

    succeeded = 0
    failed = 0
    skipped = 0
    errors: list[tuple[str, str]] = []

    for i, pdf_path in enumerate(pdf_files, 1):
        if pdf_path.name in skip_filenames:
            print(f"  [{i}/{len(pdf_files)}] SKIP {pdf_path.name} (already uploaded)")
            skipped += 1
            continue

        # Refresh headers before each upload (auto-refreshes token if expired)
        try:
            client.headers.update(auth.get_headers())
        except Exception as e:
            print(f"\nAuth error: {e}", file=sys.stderr)
            print(f"Uploaded {succeeded} files before auth failure. Use --resume to continue.")
            sys.exit(1)

        start = time.monotonic()
        try:
            with pdf_path.open("rb") as f:
                resp = client.post(
                    f"{api_url}/artifacts/upload",
                    files={"file": (pdf_path.name, f, "application/pdf")},
                    data={
                        "artifact_type": artifact_type,
                        "visibility": visibility,
                    },
                )
            resp.raise_for_status()
            result = resp.json()
            elapsed = time.monotonic() - start
            artifact_id = result.get("artifact_id", "?")
            pages = result.get("pages", [])
            page_count = len(pages) if isinstance(pages, list) else "?"
            print(
                f"  [{i}/{len(pdf_files)}] OK {pdf_path.name} -> {artifact_id} ({page_count} pages, {elapsed:.1f}s)"
            )
            succeeded += 1
        except Exception as e:
            elapsed = time.monotonic() - start
            error_msg = str(e)
            print(f"  [{i}/{len(pdf_files)}] FAIL {pdf_path.name} ({elapsed:.1f}s): {error_msg}")
            errors.append((pdf_path.name, error_msg))
            failed += 1

        if i < len(pdf_files) and delay > 0:
            time.sleep(delay)

    client.close()

    print(f"\nDone. {succeeded} succeeded, {failed} failed, {skipped} skipped.")
    if errors:
        print("\nFailed files:")
        for name, err in errors:
            print(f"  {name}: {err}")
