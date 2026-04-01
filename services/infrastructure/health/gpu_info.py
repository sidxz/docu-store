"""Shared GPU and system information utilities.

Used by both the health checker (API process) and the heartbeat reporter
(all worker processes) to collect system and GPU state.
"""

from __future__ import annotations

import importlib.metadata
import platform
import socket
import sys
import time
from datetime import UTC, datetime

import structlog

from application.dtos.health_dtos import GpuDevice, GpuInfo, SystemInfo

logger = structlog.get_logger()


def get_system_info(start_time: float, now: datetime | None = None) -> SystemInfo:
    """Collect system information for this process.

    Args:
        start_time: Monotonic time when the process started (``time.monotonic()``).
        now: Current UTC datetime.  Defaults to ``datetime.now(UTC)``.

    """
    if now is None:
        now = datetime.now(tz=UTC)

    try:
        app_version = importlib.metadata.version("docu-store")
    except importlib.metadata.PackageNotFoundError:
        app_version = "0.1.0-dev"

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
