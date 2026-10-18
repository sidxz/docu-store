import contextlib
import io
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from application.ports.blob_store import StoredBlob
from domain.value_objects.mime_type import MimeType
from infrastructure.file_services.libreoffice_converter import (
    LibreOfficeConverter,
    find_soffice,
)


class FakeBlob:
    """Blob store with on-disk source files (so get_file yields a real path)."""

    def __init__(self):
        self.sources: dict[str, bytes] = {}
        self.puts: dict[str, bytes] = {}

    def put_source(self, key, data):
        self.sources[key] = data

    @contextlib.contextmanager
    def get_file(self, key):
        d = tempfile.mkdtemp()
        p = os.path.join(d, os.path.basename(key))
        Path(p).write_bytes(self.sources[key])
        yield Path(p)

    def put_stream(self, key, stream, *, mime_type=None):
        self.puts[key] = stream.read()
        return StoredBlob(key=key, size_bytes=len(self.puts[key]), sha256="x", mime_type=mime_type)


class _FakeSoffice(LibreOfficeConverter):
    """Overrides the one external boundary: simulate LibreOffice writing <stem>.pdf."""

    def _run(self, src_path, outdir, infilter):
        (Path(outdir) / f"{Path(src_path).stem}.pdf").write_bytes(b"%PDF-1.4 fake")


def test_convert_to_pdf_stores_pdf_at_dest_key():
    blob = FakeBlob()
    blob.put_source("artifacts/x/source.pptx", b"pptx-bytes")
    conv = _FakeSoffice(blob_store=blob, soffice_bin="/bin/true")

    conv.convert_to_pdf("artifacts/x/source.pptx", "artifacts/x/derived/render.pdf", MimeType.PPTX)

    assert blob.puts["artifacts/x/derived/render.pdf"].startswith(b"%PDF")


def test_convert_raises_when_no_pdf_produced():
    class _NoOutput(LibreOfficeConverter):
        def _run(self, src_path, outdir, infilter):
            pass  # produce nothing

    blob = FakeBlob()
    blob.put_source("artifacts/x/source.pptx", b"pptx-bytes")
    conv = _NoOutput(blob_store=blob, soffice_bin="/bin/true")

    with pytest.raises(RuntimeError):
        conv.convert_to_pdf(
            "artifacts/x/source.pptx", "artifacts/x/derived/render.pdf", MimeType.PPTX
        )


@pytest.mark.skipif(find_soffice() is None, reason="LibreOffice not installed")
def test_real_soffice_converts_pptx():
    from pptx import Presentation

    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Hello"
    buf = io.BytesIO()
    prs.save(buf)

    blob = FakeBlob()
    blob.put_source("artifacts/x/source.pptx", buf.getvalue())
    conv = LibreOfficeConverter(blob_store=blob)

    conv.convert_to_pdf("artifacts/x/source.pptx", "artifacts/x/derived/render.pdf", MimeType.PPTX)

    assert blob.puts["artifacts/x/derived/render.pdf"].startswith(b"%PDF")


def test_soffice_does_not_inherit_secrets(monkeypatch, tmp_path):
    import infrastructure.file_services.libreoffice_converter as mod

    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    seen = {}
    monkeypatch.setattr(mod.subprocess, "run", lambda *_, **kw: seen.update(kw))

    LibreOfficeConverter(blob_store=FakeBlob(), soffice_bin="/bin/true")._run(
        tmp_path / "x.pptx", str(tmp_path), "MS Word 2007 XML"
    )

    assert "OPENAI_API_KEY" not in seen["env"]
    assert "PATH" in seen["env"]


def _png(color):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 40), color).save(buf, "PNG")
    return buf.getvalue()


def _linked_picture_docx(targets):
    """DOCX with one embedded picture, then pictures that are links (Word's "Link to File")."""
    import docx
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml.ns import qn

    d = docx.Document()
    d.add_picture(io.BytesIO(_png("green")))
    for target in targets:
        d.add_picture(io.BytesIO(_png("green")))
        blip = d.inline_shapes[-1]._inline.graphic.graphicData.pic.blipFill.blip
        blip.attrib.pop(qn("r:embed"))
        blip.set(qn("r:link"), d.part.relate_to(target, RT.IMAGE, is_external=True))
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


@pytest.mark.skipif(find_soffice() is None, reason="LibreOffice not installed")
def test_real_soffice_never_fetches_linked_content(tmp_path):
    import http.server
    import threading

    import fitz

    hits = []

    class Listener(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(_png("blue"))

        def log_message(self, *_):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Listener)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    local = tmp_path / "local.png"
    local.write_bytes(_png("red"))

    blob = FakeBlob()
    blob.put_source(
        "artifacts/x/source.docx",
        _linked_picture_docx(
            [local.as_uri(), f"http://127.0.0.1:{server.server_address[1]}/x.png"]
        ),
    )
    conv = LibreOfficeConverter(blob_store=blob)
    try:
        conv.convert_to_pdf(
            "artifacts/x/source.docx", "artifacts/x/derived/render.pdf", MimeType.DOCX
        )
    finally:
        server.shutdown()

    pdf = fitz.open(stream=blob.puts["artifacts/x/derived/render.pdf"], filetype="pdf")
    assert hits == []
    assert sum(len(page.get_images()) for page in pdf) == 1  # the embedded one only


@pytest.mark.skipif(find_soffice() is None, reason="LibreOffice not installed")
def test_real_soffice_refuses_content_that_is_not_the_declared_format(tmp_path):
    # A real ODT would convert fine if LibreOffice sniffed its type; the declared
    # DOCX filter must make it fail instead.
    src = tmp_path / "t.txt"
    src.write_text("hello")
    subprocess.run(
        [
            find_soffice(),
            "--headless",
            f"-env:UserInstallation=file://{tmp_path}/p",
            "--convert-to",
            "odt",
            "--outdir",
            str(tmp_path),
            str(src),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    blob = FakeBlob()
    blob.put_source("artifacts/x/source.docx", (tmp_path / "t.odt").read_bytes())
    conv = LibreOfficeConverter(blob_store=blob)

    with pytest.raises(RuntimeError):
        conv.convert_to_pdf(
            "artifacts/x/source.docx", "artifacts/x/derived/render.pdf", MimeType.DOCX
        )


def test_soffice_runs_under_resource_limits_where_prlimit_exists(monkeypatch, tmp_path):
    import infrastructure.file_services.libreoffice_converter as mod

    monkeypatch.setattr(mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    seen = {}
    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **_: seen.update(cmd=cmd))

    LibreOfficeConverter(blob_store=FakeBlob(), soffice_bin="/opt/soffice", timeout_s=180)._run(
        tmp_path / "x.pptx", str(tmp_path), "MS Word 2007 XML"
    )

    cmd = seen["cmd"]
    assert cmd[0] == "/usr/bin/prlimit"
    assert "--cpu=180" in cmd
    assert any(a.startswith("--as=") for a in cmd)
    assert cmd[cmd.index("--") + 1] == "/opt/soffice"
