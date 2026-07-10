"""Liveness file: proof the worker loop is actually running, for container healthchecks.

A hung worker looks "Running" to Swarm (2026-07-08 outage: 31h silent, backlog of
1500). The reporter touches a local file every tick; a healthcheck on the file's
mtime catches a frozen event loop in minutes.
"""

import asyncio
import contextlib
from pathlib import Path

import pytest

from infrastructure.health.heartbeat_reporter import HeartbeatReporter


def _reporter(tmp_path: Path, **kw) -> HeartbeatReporter:
    return HeartbeatReporter(
        mongo_uri="mongodb://unused:27017",
        mongo_db="unused",
        worker_type="test",
        worker_name="Test Worker",
        interval_seconds=0,
        liveness_file=str(tmp_path / "liveness"),
        **kw,
    )


@pytest.mark.asyncio
async def test_run_forever_touches_liveness_file_even_when_mongo_write_fails(
    tmp_path, monkeypatch
):
    reporter = _reporter(tmp_path)
    monkeypatch.setattr(
        reporter, "_write_heartbeat_sync", lambda **_: (_ for _ in ()).throw(OSError("mongo down"))
    )
    monkeypatch.setattr(reporter, "_delete_heartbeat_sync", lambda: None)

    task = asyncio.create_task(reporter.run_forever())
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert (tmp_path / "liveness").exists()


def test_sync_loop_touches_liveness_file(tmp_path, monkeypatch):
    reporter = _reporter(tmp_path)
    monkeypatch.setattr(reporter, "_write_heartbeat_sync", lambda **_: None)

    reporter.start_sync_background()
    try:
        for _ in range(50):  # up to ~0.5s for the daemon thread to tick
            if (tmp_path / "liveness").exists():
                break
            import time

            time.sleep(0.01)
    finally:
        monkeypatch.setattr(reporter, "_delete_heartbeat_sync", lambda: None)
        reporter.stop()

    assert (tmp_path / "liveness").exists()
