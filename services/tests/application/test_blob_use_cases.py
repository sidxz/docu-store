import bz2
import io
import struct
import tracemalloc
import zipfile
from uuid import uuid4

from returns.result import Failure, Success

from application.dtos.blob_dtos import UploadBlobRequest
from application.ports.blob_store import StoredBlob
from application.use_cases.blob_use_cases import UploadBlobUseCase
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType

DOCX_MAIN = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
PPTX_MAIN = "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
DOCM_MAIN = "application/vnd.ms-word.document.macroEnabled.main+xml"
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n"
WS = uuid4()


class FakeBlobStore:
    def __init__(self):
        self.keys: list[str] = []

    def put_stream(self, key, stream, *, mime_type=None):
        data = stream.read()
        self.keys.append(key)
        return StoredBlob(key=key, size_bytes=len(data), sha256="x", mime_type=mime_type)


def _ooxml(main_ct=DOCX_MAIN, parts=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            f'<Types><Override PartName="/main.xml" ContentType="{main_ct}"/></Types>',
        )
        for name, data in (parts or {"main.xml": b"<x/>"}).items():
            z.writestr(name, data)
    return buf.getvalue()


def _upload(data, declared=MimeType.DOCX.value, filename="upload.bin"):
    blob = FakeBlobStore()
    req = UploadBlobRequest(
        artifact_type=ArtifactType.RESEARCH_ARTICLE, filename=filename, mime_type=declared
    )
    return UploadBlobUseCase(blob_store=blob).execute(io.BytesIO(data), req, WS), blob


def test_pdf_is_identified_by_content_not_declared_type():
    result, blob = _upload(PDF, declared="application/octet-stream")
    assert isinstance(result, Success)
    assert result.unwrap().mime_type == MimeType.PDF.value
    assert blob.keys[0].endswith("/source.pdf")


def test_docx_and_pptx_are_told_apart_by_main_part():
    docx, _ = _upload(_ooxml(DOCX_MAIN), filename="x.pdf")
    pptx, blob = _upload(_ooxml(PPTX_MAIN))
    assert docx.unwrap().mime_type == MimeType.DOCX.value
    assert pptx.unwrap().mime_type == MimeType.PPTX.value
    assert blob.keys[0].endswith("/source.pptx")


def test_rejects_non_document_declared_as_pdf():
    result, blob = _upload(b"<html><script>alert(1)</script></html>", declared="application/pdf")
    assert isinstance(result, Failure)
    assert blob.keys == []


def test_rejects_legacy_or_encrypted_ole2():
    result, _ = _upload(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 512)
    assert isinstance(result, Failure)


def test_rejects_macro_enabled_ooxml():
    result, _ = _upload(_ooxml(DOCM_MAIN))
    assert isinstance(result, Failure)


def test_rejects_vba_project_even_under_a_docx_content_type():
    result, _ = _upload(_ooxml(parts={"main.xml": b"<x/>", "word/vbaProject.bin": b"vba"}))
    assert isinstance(result, Failure)


def test_rejects_activex_parts():
    result, _ = _upload(_ooxml(parts={"main.xml": b"<x/>", "word/activeX/activeX1.xml": b"<x/>"}))
    assert isinstance(result, Failure)


def test_rejects_odf_renamed_to_docx():
    odf = _ooxml(parts={"mimetype": b"application/vnd.oasis.opendocument.text", "main.xml": b"<x/>"})
    result, _ = _upload(odf, declared=MimeType.DOCX.value)
    assert isinstance(result, Failure)


def test_rejects_parts_that_unpack_past_1_gib():
    data = bytearray(_ooxml(parts={"main.xml": b"<x/>", "word/big.xml": b"<x/>"}))
    cd = data.rindex(b"word/big.xml") - 46  # its central-directory record
    struct.pack_into("<L", data, cd + 24, 2**31)  # claimed uncompressed size
    result, _ = _upload(bytes(data))
    assert isinstance(result, Failure)
    assert "1 GiB" in result.failure().message


def test_accepts_honestly_well_compressed_media():
    """Real decks embed uncompressed TIFF/EMF images that deflate 100-300:1."""
    result, _ = _upload(_ooxml(PPTX_MAIN, parts={"main.xml": b"<x/>", "ppt/media/image1.tif": b"\0" * 5_000_000}))
    assert isinstance(result, Success)


def test_rejects_path_traversal_entry():
    result, _ = _upload(_ooxml(parts={"main.xml": b"<x/>", "../evil.xml": b"<x/>"}))
    assert isinstance(result, Failure)


def _peak_mib(fn):
    tracemalloc.start()
    try:
        result = fn()
        return result, tracemalloc.get_traced_memory()[1] / 2**20
    finally:
        tracemalloc.stop()


def _lying_bzip2_docx():
    """[Content_Types].xml is 64 MiB of zeros under bzip2, headers claim 1000 bytes."""
    payload, name = bz2.compress(b"\0" * 64 * 2**20, 9), b"[Content_Types].xml"
    local = struct.pack("<4s5H3L2H", b"PK\x03\x04", 46, 0, 12, 0, 0, 0, len(payload), 1000, len(name), 0)
    central = struct.pack(
        "<4s6H3L5H2L", b"PK\x01\x02", 46, 46, 0, 12, 0, 0, 0, len(payload), 1000, len(name), 0, 0, 0, 0, 0, 0
    )
    cd_at = len(local) + len(name) + len(payload)
    eocd = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 1, 1, len(central) + len(name), cd_at, 0)
    return local + name + payload + central + name + eocd


def test_rejects_lying_bomb_without_unpacking_it():
    bomb = _lying_bzip2_docx()
    (result, _), peak = _peak_mib(lambda: _upload(bomb))
    assert isinstance(result, Failure)
    assert peak < 16


def test_rejects_too_many_parts_before_listing_them():
    """60k central-directory records behind an end record that admits to one."""
    name = b"p.xml"
    rec = struct.pack("<4s6H3L5H2L", b"PK\x01\x02", 20, 20, 0, 0, 0, 0, 0, 0, 0, len(name), 0, 0, 0, 0, 0, 0)
    cd = (rec + name) * 60_000
    head = b"PK\x03\x04" + b"\0" * 26
    eocd = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 1, 1, len(cd), len(head), 0)
    upload = head + cd + eocd
    (result, _), peak = _peak_mib(lambda: _upload(upload))
    assert isinstance(result, Failure)
    assert peak < 16


def test_rejects_vba_project_found_through_its_relationship():
    rels = (
        b'<Relationships><Relationship Id="r1" Target="x.bin" '
        b'Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject"/></Relationships>'
    )
    result, _ = _upload(_ooxml(parts={"main.xml": b"<x/>", "word/_rels/main.xml.rels": rels, "word/x.bin": b"vba"}))
    assert isinstance(result, Failure)


def test_rejects_macro_content_type_spelled_with_a_character_reference():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            f'<Types><Override PartName="/main.xml" ContentType="{DOCX_MAIN}"/>'
            '<Override PartName="/m.xml" ContentType="application/vnd.ms-word.document.macro&#69;nabled.main+xml"/>'
            "</Types>",
        )
        z.writestr("main.xml", "<x/>")
        z.writestr("m.xml", "<x/>")
    result, _ = _upload(buf.getvalue())
    assert isinstance(result, Failure)


def test_zip_with_pdf_marker_is_judged_as_ooxml():
    result, _ = _upload(_ooxml(DOCM_MAIN, parts={"%PDF-1.7.xml": b"<x/>"}))
    assert isinstance(result, Failure)
