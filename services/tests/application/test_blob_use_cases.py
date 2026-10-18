import io
import zipfile

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
    return UploadBlobUseCase(blob_store=blob).execute(io.BytesIO(data), req), blob


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
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr("content.xml", "<x/>")
    result, _ = _upload(buf.getvalue(), declared=MimeType.DOCX.value)
    assert isinstance(result, Failure)


def test_rejects_zip_bomb_by_compression_ratio():
    result, _ = _upload(_ooxml(parts={"main.xml": b"<x/>", "word/bomb.xml": b"\0" * 5_000_000}))
    assert isinstance(result, Failure)


def test_rejects_path_traversal_entry():
    result, _ = _upload(_ooxml(parts={"main.xml": b"<x/>", "../evil.xml": b"<x/>"}))
    assert isinstance(result, Failure)
