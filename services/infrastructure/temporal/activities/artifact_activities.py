"""Toy activities for artifact processing workflow.

These activities are invoked by the Temporal workflow. Each activity
encapsulates a unit of work that can be retried independently.

For now, these are logging activities to demonstrate the structure.
In production, these would call use cases to persist results to domain.
"""

from __future__ import annotations

import structlog
from temporalio import activity

logger = structlog.get_logger()


@activity.defn
async def log_mime_type_activity(mime_type: str) -> str:
    """Activity that logs the MIME type of the artifact.

    In a real workflow, this might:
    - Validate MIME type support
    - Route to appropriate parser

    Args:
        mime_type: The MIME type to log

    Returns:
        A confirmation message

    """
    logger.info("activity_log_mime_type", mime_type=mime_type)
    return f"Logged MIME type: {mime_type}"


@activity.defn
async def log_storage_location_activity(storage_location: str) -> str:
    """Activity that logs the storage location of the artifact.

    In a real workflow, this might:
    - Verify blob store access
    - Validate file exists
    - Check file size

    Args:
        storage_location: The path/location where artifact is stored

    Returns:
        A confirmation message

    """
    logger.info("activity_log_storage_location", storage_location=storage_location)
    return f"Logged storage location: {storage_location}"
