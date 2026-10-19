import io

import pytest

from infrastructure.blob_stores.fsspec_blob_store import FsspecBlobStore


@pytest.mark.parametrize("key", ["../secret", "artifacts/../../secret", "/secret"])
def test_keys_cannot_leave_the_store(tmp_path, key):
    (tmp_path / "secret").write_bytes(b"outside the store")
    store = FsspecBlobStore(f"file://{tmp_path / 'blobs'}")
    with pytest.raises(ValueError, match="blob key"):
        store.get_bytes(key)


def test_ordinary_keys_round_trip(tmp_path):
    store = FsspecBlobStore(f"file://{tmp_path}")
    store.put_stream("artifacts/a/source.pdf", io.BytesIO(b"%PDF-1.7"))
    assert store.get_bytes("artifacts/a/source.pdf") == b"%PDF-1.7"
