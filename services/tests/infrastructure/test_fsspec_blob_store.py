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


def test_total_size_sums_every_file_under_a_prefix(tmp_path):
    store = FsspecBlobStore(f"file://{tmp_path}")
    store.put_stream("workspaces/w/artifacts/a/source.pdf", io.BytesIO(b"12345"))
    store.put_stream("workspaces/w/artifacts/a/pages/0.png", io.BytesIO(b"123"))
    store.put_stream("workspaces/other/artifacts/b/source.pdf", io.BytesIO(b"1"))
    assert store.total_size("workspaces/w") == 8


def test_total_size_of_missing_prefix_is_zero(tmp_path):
    assert FsspecBlobStore(f"file://{tmp_path}").total_size("workspaces/none") == 0


def test_delete_prefix_removes_the_whole_folder_only(tmp_path):
    store = FsspecBlobStore(f"file://{tmp_path}")
    store.put_stream("workspaces/w/artifacts/a/pages/0.png", io.BytesIO(b"1"))
    store.put_stream("workspaces/w/artifacts/b/source.pdf", io.BytesIO(b"1"))
    store.delete_prefix("workspaces/w/artifacts/a")
    assert not store.exists("workspaces/w/artifacts/a/pages/0.png")
    assert store.exists("workspaces/w/artifacts/b/source.pdf")


def test_delete_prefix_of_missing_folder_is_silent(tmp_path):
    FsspecBlobStore(f"file://{tmp_path}").delete_prefix("workspaces/w/artifacts/gone")


@pytest.mark.parametrize("prefix", ["", "/"])
def test_delete_prefix_refuses_the_store_root(tmp_path, prefix):
    with pytest.raises(ValueError):
        FsspecBlobStore(f"file://{tmp_path}").delete_prefix(prefix)


@pytest.mark.parametrize("prefix", ["../x", "/x", "workspaces/../../x"])
def test_prefix_calls_refuse_escaping_keys(tmp_path, prefix):
    with pytest.raises(ValueError, match="blob key"):
        FsspecBlobStore(f"file://{tmp_path}").total_size(prefix)
