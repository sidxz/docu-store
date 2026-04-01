"""One-time script to generate JPEG thumbnails for existing page images.

Scans blob storage for full-resolution PNGs that lack a corresponding
_thumb.jpg and generates lightweight thumbnails (200px wide, JPEG 75%).

Usage:
    uv run python scripts/backfill_thumbnails.py [--dry-run]
"""

import io
import re
import sys

import fsspec
from PIL import Image

from infrastructure.blob_stores.fsspec_blob_store import FsspecBlobStore
from infrastructure.config import settings

THUMBNAIL_MAX_WIDTH = 400
THUMBNAIL_JPEG_QUALITY = 85
PAGE_PNG_PATTERN = re.compile(r"^artifacts/[^/]+/pages/\d+\.png$")


def make_thumbnail(png_bytes: bytes) -> io.BytesIO:
    """Resize a full-resolution PNG to a small JPEG thumbnail."""
    with Image.open(io.BytesIO(png_bytes)) as img:
        img = img.convert("RGB")
        w, h = img.size
        if w > THUMBNAIL_MAX_WIDTH:
            ratio = THUMBNAIL_MAX_WIDTH / w
            img = img.resize(
                (THUMBNAIL_MAX_WIDTH, int(h * ratio)),
                Image.LANCZOS,
            )
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=THUMBNAIL_JPEG_QUALITY)
        buf.seek(0)
        return buf


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    blob_store = FsspecBlobStore(
        base_url=settings.blob_base_url,
        storage_options=settings.blob_storage_options,
    )

    # List all page PNGs via fsspec glob
    base_url = blob_store.base_url
    fs, _ = fsspec.core.url_to_fs(base_url, **blob_store.storage_options)
    _, base_path = fsspec.core.url_to_fs(base_url, **blob_store.storage_options)
    all_files = fs.glob(f"{base_path}/artifacts/*/pages/*.png")

    # Filter to only page PNGs (exclude _thumb files)
    page_pngs = []
    for f in all_files:
        # Get the relative key from the full path
        rel = f.replace(base_path + "/", "") if f.startswith(base_path) else f
        if PAGE_PNG_PATTERN.match(rel):
            page_pngs.append(rel)

    print(f"Found {len(page_pngs)} page PNG(s)")

    created = 0
    skipped = 0
    failed = 0

    for png_key in page_pngs:
        thumb_key = png_key.replace(".png", "_thumb.jpg")

        if blob_store.exists(thumb_key):
            skipped += 1
            continue

        if dry_run:
            print(f"  [dry-run] Would create: {thumb_key}")
            created += 1
            continue

        try:
            png_bytes = blob_store.get_bytes(png_key)
            thumb_buf = make_thumbnail(png_bytes)
            blob_store.put_stream(thumb_key, thumb_buf, mime_type="image/jpeg")
            created += 1
            print(f"  Created: {thumb_key}")
        except Exception as e:
            failed += 1
            print(f"  FAILED: {png_key} — {e}")

    print(f"\nDone: {created} created, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()
