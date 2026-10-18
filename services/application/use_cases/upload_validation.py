"""Identify an upload by its bytes, never by the client's Content-Type.

Only PDF and OOXML (DOCX/PPTX) pass. OOXML is judged from the zip central
directory plus [Content_Types].xml; nothing else is unpacked here.
"""

import zipfile
from typing import BinaryIO

from domain.exceptions import ValidationError
from domain.value_objects.mime_type import MimeType

_DOCX_MAIN = "wordprocessingml.document.main+xml"
_PPTX_MAIN = "presentationml.presentation.main+xml"

# ponytail: sizes come from zip headers, which a crafted file can understate;
# the converter's rlimits are the backstop for a lying bomb.
_MAX_ENTRIES = 10_000
_MAX_UNPACKED = 2**30
_MAX_RATIO = 100  # Apache POI's default (1% minimum inflate ratio)
_RATIO_GRACE = 100_000  # small parts are allowed to compress better


def detect_document_type(stream: BinaryIO) -> MimeType:
    """Return the upload's real type, or raise ValidationError. Rewinds the stream."""
    head = stream.read(1024)
    stream.seek(0)
    if b"%PDF-" in head:
        return MimeType.PDF
    if head.startswith(b"PK\x03\x04"):
        try:
            return _ooxml_type(stream)
        finally:
            stream.seek(0)
    # Legacy .doc/.ppt and encrypted OOXML are OLE2 containers and land here too.
    msg = "Only PDF, DOCX and PPTX files are accepted"
    raise ValidationError(msg)


def _ooxml_type(stream: BinaryIO) -> MimeType:
    try:
        with zipfile.ZipFile(stream) as z:
            infos = z.infolist()
            _check_entries(infos)
            content_types = z.read("[Content_Types].xml").decode("utf-8", "replace")
    except ValidationError:
        raise
    except Exception as e:  # BadZipFile, missing part, encrypted entry, …
        msg = f"Not a readable DOCX or PPTX file ({e})"
        raise ValidationError(msg) from e

    if "macroenabled" in content_types.lower():
        msg = "Macro-enabled documents are not accepted"
        raise ValidationError(msg)
    is_docx, is_pptx = _DOCX_MAIN in content_types, _PPTX_MAIN in content_types
    if is_docx == is_pptx:
        msg = "Not a DOCX or PPTX file"
        raise ValidationError(msg)
    return MimeType.DOCX if is_docx else MimeType.PPTX


def _check_entries(infos: list[zipfile.ZipInfo]) -> None:
    if len(infos) > _MAX_ENTRIES:
        msg = f"Document has more than {_MAX_ENTRIES} parts"
        raise ValidationError(msg)
    total = 0
    for info in infos:
        name = info.filename
        lower = f"/{name.lower()}"
        if name.startswith("/") or ".." in name.split("/"):
            msg = f"Document contains an unsafe part path: {name}"
            raise ValidationError(msg)
        if name == "mimetype":  # an OpenDocument file wearing an OOXML name
            msg = "OpenDocument files are not accepted"
            raise ValidationError(msg)
        if lower.endswith("/vbaproject.bin") or "/activex/" in lower:
            msg = "Documents with macros or ActiveX controls are not accepted"
            raise ValidationError(msg)
        if info.file_size > _RATIO_GRACE and info.file_size > _MAX_RATIO * max(
            info.compress_size, 1
        ):
            msg = "Document is compressed suspiciously well (possible zip bomb)"
            raise ValidationError(msg)
        total += info.file_size
    if total > _MAX_UNPACKED:
        msg = "Document unpacks to more than 1 GiB"
        raise ValidationError(msg)
