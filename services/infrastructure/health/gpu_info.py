"""Shared GPU and system information utilities.

Used by both the health checker (API process) and the heartbeat reporter
(all worker processes) to collect system and GPU state.
"""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
import platform
import socket
import sys
import time
from datetime import UTC, datetime

import structlog

from application.dtos.health_dtos import GpuDevice, GpuInfo, SystemInfo

logger = structlog.get_logger()


def _get_app_version() -> str:
    """Read the version from pyproject.toml (source of truth), falling back to installed metadata."""
    # pyproject.toml lives at the services/ root, one level above infrastructure/
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if pyproject.is_file():
        for line in pyproject.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("version"):
                # version = "0.2.1"
                _, _, value = stripped.partition("=")
                return value.strip().strip('"').strip("'")

    try:
        return importlib.metadata.version("docu-store")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0-dev"


def get_system_info(start_time: float, now: datetime | None = None) -> SystemInfo:
    """Collect system information for this process.

    Args:
        start_time: Monotonic time when the process started (``time.monotonic()``).
        now: Current UTC datetime.  Defaults to ``datetime.now(UTC)``.

    """
    if now is None:
        now = datetime.now(tz=UTC)

    app_version = _get_app_version()

    return SystemInfo(
        app_version=app_version,
        python_version=sys.version.split()[0],
        os_info=f"{platform.system()} {platform.release()} ({platform.machine()})",
        hostname=socket.gethostname(),
        uptime_seconds=round(time.monotonic() - start_time, 1),
        timestamp=now.isoformat(),
    )


def get_gpu_info() -> GpuInfo:
    """Detect CUDA/MPS availability and per-device memory for this process."""
    try:
        import torch
    except ImportError:
        return GpuInfo(cuda_available=False, mps_available=False)

    cuda_available = torch.cuda.is_available()
    mps_available = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()

    devices: list[GpuDevice] = []
    cuda_version: str | None = None

    if cuda_available:
        cuda_version = torch.version.cuda
        for i in range(torch.cuda.device_count()):
            try:
                free, total = torch.cuda.mem_get_info(i)
                devices.append(
                    GpuDevice(
                        index=i,
                        name=torch.cuda.get_device_name(i),
                        memory_total_mb=round(total / 1024**2),
                        memory_used_mb=round((total - free) / 1024**2),
                        memory_free_mb=round(free / 1024**2),
                    )
                )
            except Exception:
                logger.warning("gpu_info_failed", device_index=i)

    return GpuInfo(
        cuda_available=cuda_available,
        mps_available=mps_available,
        cuda_version=cuda_version,
        device_count=torch.cuda.device_count() if cuda_available else 0,
        devices=devices,
    )
