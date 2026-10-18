from typing import Annotated

from fastapi import FastAPI, File, UploadFile
from fastapi.testclient import TestClient

import interfaces.api.routes  # noqa: F401 — must load before the middleware package (import cycle)
from interfaces.api.middleware.body_size_limit import BodySizeLimitMiddleware

app = FastAPI()


@app.post("/upload")
async def upload(file: Annotated[UploadFile, File()]) -> dict:
    return {"size": len(await file.read())}


app.add_middleware(BodySizeLimitMiddleware, max_bytes=1000)
client = TestClient(app)


def test_small_upload_passes():
    r = client.post("/upload", files={"file": ("a.pdf", b"x" * 100)})
    assert r.status_code == 200
    assert r.json() == {"size": 100}


def test_declared_oversize_rejected():
    r = client.post("/upload", files={"file": ("a.pdf", b"x" * 2000)})
    assert r.status_code == 413


def test_chunked_oversize_rejected():
    # A generator body is sent chunked, with no Content-Length to check.
    def body():
        yield b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\n'
        for _ in range(10):
            yield b"x" * 500

    r = client.post(
        "/upload", content=body(), headers={"content-type": "multipart/form-data; boundary=b"}
    )
    assert r.status_code == 413
