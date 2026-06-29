from __future__ import annotations

import io
from typing import TYPE_CHECKING

import structlog

from application.dtos.parsed_document import Block, ParsedDocument, ParseResult, RenderedPage
from application.ports.document_parser import DocumentParser

if TYPE_CHECKING:
    from application.ports.blob_store import BlobStore

log = structlog.get_logger(__name__)

# Map Docling DocItemLabel values -> our Block.type
_LABEL_MAP: dict[str, str] = {
    "title": "heading",
    "section_header": "heading",
    "paragraph": "paragraph",
    "text": "paragraph",
    "list_item": "list",
    "table": "table",
    "picture": "figure",
    "chart": "figure",
    "caption": "caption",
    "formula": "equation",
    "code": "code",
    "footnote": "footnote",
    "reference": "reference",
}

_THUMB_MAX = 400  # px, longest edge


def _make_thumb(png: bytes) -> bytes | None:
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(png))
        img.thumbnail((_THUMB_MAX, _THUMB_MAX))
        out = io.BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=80)
        return out.getvalue()
    except Exception:
        log.warning("docling_parser.thumb_failed", exc_info=True)
        return None


class DoclingParser(DocumentParser):
    """Parse documents into a structured ParsedDocument using Docling."""

    def __init__(self, blob_store: BlobStore) -> None:
        self.blob_store = blob_store
        self._converter = None  # ponytail: lazy init, avoids model load at import time

    def _get_converter(self):
        if self._converter is None:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption

            opts = PdfPipelineOptions()
            opts.generate_page_images = True
            opts.images_scale = 2.0  # ~144 DPI
            self._converter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)},
            )
        return self._converter

    def parse(self, storage_key: str) -> ParseResult:
        with self.blob_store.get_file(storage_key) as path:
            conv = self._get_converter().convert(str(path))
        dl_doc = conv.document

        blocks: list[Block] = []
        for item, _level in dl_doc.iterate_items():
            block = self._to_block(item, dl_doc)
            if block is not None:
                blocks.append(block)

        # dl_doc.pages is dict[int, PageItem] keyed by 1-based page number
        pages: list[RenderedPage] = []
        for page_no in sorted(dl_doc.pages):
            png = self._page_png(dl_doc, page_no)
            if png is not None:
                pages.append(RenderedPage(index=page_no - 1, png=png, thumb=_make_thumb(png)))

        return ParseResult(
            document=ParsedDocument(source_mime="application/pdf", blocks=blocks),
            pages=pages,
        )

    def _to_block(self, item, dl_doc) -> Block | None:
        # item.label is a DocItemLabel enum; .value gives the string
        label_val = getattr(item.label, "value", None) if hasattr(item, "label") else None
        btype = _LABEL_MAP.get(str(label_val), "other")

        page_idx: int | None = None
        prov = getattr(item, "prov", None)
        if prov:
            page_idx = prov[0].page_no - 1  # convert 1-based to 0-based

        if btype == "table":
            return Block(type="table", rows=self._table_rows(item, dl_doc), source_page_index=page_idx)

        text = getattr(item, "text", "") or ""
        if not text and btype not in ("figure",):
            return None
        return Block(type=btype, text=text, source_page_index=page_idx)

    def _table_rows(self, item, dl_doc) -> list[list[str]]:
        try:
            df = item.export_to_dataframe(doc=dl_doc)
            return [list(df.columns)] + df.astype(str).values.tolist()
        except Exception:
            log.warning("docling_parser.table_export_failed", exc_info=True)
            return []

    def _page_png(self, dl_doc, page_no: int) -> bytes | None:
        try:
            page = dl_doc.pages[page_no]
            # page.image is ImageRef; .pil_image is a property -> Optional[PIL.Image.Image]
            pil_img = page.image.pil_image if page.image else None
            if pil_img is None:
                log.warning("docling_parser.page_image_missing", page_no=page_no)
                return None
            out = io.BytesIO()
            pil_img.convert("RGB").save(out, format="PNG")
            return out.getvalue()
        except Exception:
            log.warning("docling_parser.page_image_failed", page_no=page_no, exc_info=True)
            return None
