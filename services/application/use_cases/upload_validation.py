"""Identify an upload by its bytes, never by the client's Content-Type.

Only PDF and OOXML (DOCX/PPTX) pass. OOXML is judged from the zip central
directory, [Content_Types].xml and the relationship parts; every read is
capped, because a zip's own size headers can lie.
"""

import xml.etree.ElementTree as ET
import zipfile
from typing import BinaryIO

from domain.exceptions import ValidationError
from domain.value_objects.mime_type import MimeType

_DOCX_MAIN = "wordprocessingml.document.main+xml"
_PPTX_MAIN = "presentationml.presentation.main+xml"

_MAX_ENTRIES = 10_000
_MAX_CENTRAL_DIR = 2 * 2**20  # 10k realistic part names fit in about 1 MiB
# ponytail: header sizes can understate a bomb; reads here are capped and the
# converter's rlimits are the backstop. No per-part ratio check: real decks carry
# uncompressed TIFF/EMF images that deflate 100-300:1.
_MAX_UNPACKED = 2**30
_MAX_XML_PART = 2**20  # [Content_Types].xml and .rels parts are a few KB in practice
_MAX_XML_TOTAL = 32 * 2**20

# Content types and relationship types that carry macros or ActiveX controls.
_ACTIVE_CONTENT_TYPES = ("macroenabled", "vbaproject", "activex")
_ACTIVE_RELATIONSHIPS = ("/vbaproject", "/wordvbadata", "/activexcontrolbinary", "/control")


def detect_document_type(stream: BinaryIO) -> MimeType:
    """Return the upload's real type, or raise ValidationError. Rewinds the stream."""
    head = stream.read(1024)
    stream.seek(0)
    # Zip first: a zip that carries "%PDF-" in its first KiB is still a zip.
    if head.startswith(b"PK\x03\x04"):
        try:
            return _ooxml_type(stream)
        finally:
            stream.seek(0)
    if b"%PDF-" in head:
        return MimeType.PDF
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):  # OLE2
        msg = "Password-protected and legacy Office files (.doc, .ppt) are not accepted"
        raise ValidationError(msg)
    msg = "Only PDF, DOCX and PPTX files are accepted"
    raise ValidationError(msg)


def _ooxml_type(stream: BinaryIO) -> MimeType:
    _check_central_directory(stream)
    try:
        with zipfile.ZipFile(stream) as z:
            infos = z.infolist()
            _check_entries(infos)
            content_types = _content_types(_parse(_read_part(z, "[Content_Types].xml")))
            _check_relationships(z, infos)
    except ValidationError:
        raise
    except Exception as e:  # BadZipFile, missing part, encrypted entry, bad XML, …
        msg = f"Not a readable DOCX or PPTX file ({e})"
        raise ValidationError(msg) from e

    if any(t in ct for ct in content_types for t in _ACTIVE_CONTENT_TYPES):
        msg = "Documents with macros or ActiveX controls are not accepted"
        raise ValidationError(msg)
    is_docx = any(ct.endswith(_DOCX_MAIN) for ct in content_types)
    is_pptx = any(ct.endswith(_PPTX_MAIN) for ct in content_types)
    if is_docx == is_pptx:
        msg = "Not a DOCX or PPTX file"
        raise ValidationError(msg)
    return MimeType.DOCX if is_docx else MimeType.PPTX


def _check_central_directory(stream: BinaryIO) -> None:
    """Bound the part list from the end record, before zipfile builds it.

    zipfile walks the central directory by its byte size, not the entry count,
    and follows a zip64 locator if one precedes the end record, so all three
    are checked. No document under the upload cap needs zip64.
    """
    stream.seek(0, 2)
    size = stream.tell()
    tail_len = min(size, 22 + 0xFFFF)
    stream.seek(size - tail_len)
    tail = stream.read(tail_len)
    stream.seek(0)
    at = tail.rfind(b"PK\x05\x06")
    if at < 0 or len(tail) - at < 22:
        msg = "Not a readable DOCX or PPTX file"
        raise ValidationError(msg)
    entries = int.from_bytes(tail[at + 10 : at + 12], "little")
    cd_size = int.from_bytes(tail[at + 12 : at + 16], "little")
    zip64 = at >= 20 and tail[at - 20 : at - 16] == b"PK\x06\x07"
    if zip64 or entries > _MAX_ENTRIES or cd_size > _MAX_CENTRAL_DIR:
        msg = f"Document has more than {_MAX_ENTRIES} parts"
        raise ValidationError(msg)


def _read_part(z: zipfile.ZipFile, name: str) -> bytes:
    with z.open(name) as f:
        data = f.read(_MAX_XML_PART + 1)
    if len(data) > _MAX_XML_PART:
        msg = f"Document part is too large: {name}"
        raise ValidationError(msg)
    return data


def _parse(data: bytes) -> ET.Element:
    # Safe: expat (>= 2.4.1) caps entity amplification, ElementTree resolves no
    # external entities, and _read_part caps the input.
    return ET.fromstring(data)  # noqa: S314


def _content_types(root: ET.Element) -> list[str]:
    return [el.get("ContentType", "").lower() for el in root.iter() if el.get("ContentType")]


def _check_relationships(z: zipfile.ZipFile, infos: list[zipfile.ZipInfo]) -> None:
    """Macros and ActiveX are found through relationship types, not part names."""
    budget = _MAX_XML_TOTAL  # counts bytes actually read; header sizes can lie
    for info in infos:
        if not info.filename.lower().endswith(".rels"):
            continue
        data = _read_part(z, info.filename)
        budget -= len(data)
        if budget < 0:
            msg = "Document has too many relationship parts"
            raise ValidationError(msg)
        for el in _parse(data).iter():
            if el.get("Type", "").lower().endswith(_ACTIVE_RELATIONSHIPS):
                msg = "Documents with macros or ActiveX controls are not accepted"
                raise ValidationError(msg)


def _check_entries(infos: list[zipfile.ZipInfo]) -> None:
    if len(infos) > _MAX_ENTRIES:
        msg = f"Document has more than {_MAX_ENTRIES} parts"
        raise ValidationError(msg)
    total = 0
    for info in infos:
        name = info.filename
        lower = f"/{name.lower()}"
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            # bzip2/LZMA inflate without an output bound; OOXML never uses them.
            msg = f"Document part uses an unsupported compression method: {name}"
            raise ValidationError(msg)
        if name.startswith("/") or ".." in name.split("/"):
            msg = f"Document contains an unsafe part path: {name}"
            raise ValidationError(msg)
        if name == "mimetype":  # an OpenDocument file wearing an OOXML name
            msg = "OpenDocument files are not accepted"
            raise ValidationError(msg)
        if lower.endswith("/vbaproject.bin") or "/activex/" in lower:
            msg = "Documents with macros or ActiveX controls are not accepted"
            raise ValidationError(msg)
        total += info.file_size
    if total > _MAX_UNPACKED:
        msg = "Document unpacks to more than 1 GiB"
        raise ValidationError(msg)
